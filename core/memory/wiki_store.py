"""WikiStore: filesystem-backed markdown wiki for agents.

Handles read/write/list/search and git autocommit. Path escape attempts
(e.g. '../') are rejected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class WikiStore:
    def __init__(self, root: str | Path, *, autocommit: bool = True):
        self.root = Path(root).resolve()
        self.autocommit = autocommit
        self.root.mkdir(parents=True, exist_ok=True)

    # ----- path safety -----

    def _resolve(self, relpath: str) -> Path:
        p = (self.root / relpath).resolve()
        try:
            p.relative_to(self.root)
        except ValueError:
            raise ValueError(f"path escapes wiki root: {relpath}")
        return p

    # ----- basic ops -----

    def read(self, relpath: str) -> str:
        p = self._resolve(relpath)
        if not p.exists():
            raise FileNotFoundError(relpath)
        return p.read_text(encoding="utf-8")

    def write(self, relpath: str, content: str) -> None:
        p = self._resolve(relpath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        if self.autocommit:
            self._git_commit_push(f"wiki: update {relpath}")

    def list(self, folder: str = "") -> list[str]:
        base = self._resolve(folder) if folder else self.root
        if not base.exists():
            return []
        out: list[str] = []
        for p in base.rglob("*.md"):
            out.append(str(p.relative_to(self.root)).replace("\\", "/"))
        return out

    def search(self, query: str) -> list[dict]:
        q = query.lower()
        hits: list[dict] = []
        for rel in self.list():
            text = self.read(rel)
            if q in text.lower():
                idx = text.lower().find(q)
                start = max(0, idx - 40)
                end = min(len(text), idx + 80)
                snippet = text[start:end].replace("\n", " ")
                hits.append({"path": rel, "snippet": snippet})
        return hits

    # ----- log & index (implemented in task 2.2) -----

    def append_log(self, kind: str, title: str, body: str) -> None:
        ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{ts}] {kind} | {title}\n{body}\n"
        p = self._resolve("log.md")
        if not p.exists():
            p.write_text("# Wiki Log\n\n", encoding="utf-8")
        with p.open("a", encoding="utf-8") as f:
            f.write(entry)
        if self.autocommit:
            self._git_commit_push(f"wiki-log: {kind} | {title}")

    def update_index(self, path: str, summary: str) -> None:
        p = self._resolve("index.md")
        if not p.exists():
            p.write_text("# Wiki Index\n\n", encoding="utf-8")
        existing = p.read_text(encoding="utf-8").splitlines()

        # Drop any existing line that references this path
        label = Path(path).stem
        keep = [ln for ln in existing if f"({path})" not in ln]

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_line = f"- [{label}]({path}) — {summary} ({date_str})"
        keep.append(new_line)

        p.write_text("\n".join(keep) + "\n", encoding="utf-8")
        if self.autocommit:
            self._git_commit_push(f"wiki-index: {path}")

    # ----- git -----

    def _git_commit_push(self, message: str) -> None:
        """Fire-and-forget git add/commit/push. Silent on failure (logged to stderr)."""
        import subprocess
        import sys

        try:
            subprocess.run(
                ["git", "-C", str(self.root), "add", "-A"],
                check=True, capture_output=True, text=True, timeout=10,
            )
            result = subprocess.run(
                [
                    "git", "-C", str(self.root),
                    "-c", "user.email=isaac@conexus.bot",
                    "-c", "user.name=Isaac (Conexus)",
                    "commit", "-m", message,
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0 and "nothing to commit" not in result.stdout:
                print(f"[wiki] commit failed: {result.stdout} {result.stderr}", file=sys.stderr)
                return
            branch_result = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            branch = branch_result.stdout.strip() or "main"
            # Skip push if no remote is configured (e.g. local-only wiki in dev)
            remote_check = subprocess.run(
                ["git", "-C", str(self.root), "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5,
            )
            if remote_check.returncode != 0:
                return
            push = subprocess.run(
                ["git", "-C", str(self.root), "push", "origin", branch],
                capture_output=True, text=True, timeout=30,
            )
            if push.returncode != 0:
                print(f"[wiki] push failed (rc={push.returncode}): {push.stderr[:300]}", file=sys.stderr)
            else:
                print(f"[wiki] pushed OK: {message}", flush=True)
        except Exception as e:
            print(f"[wiki] git sync error: {e}", file=sys.stderr)
