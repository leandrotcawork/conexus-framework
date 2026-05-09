"""GitHub App wiki backend — per-agent repo, git-backed."""
from __future__ import annotations

import subprocess
from pathlib import Path

from conexus.core.memory.wiki.git_auth import get_installation_token
from conexus.core.memory.wiki.local import LocalBackend


class GitHubAppBackend:
    """Sync WikiBackend backed by a GitHub repo via App installation tokens.

    Tech debt: git subprocess calls block the event loop.
    Acceptable for single-user MVP; wrap in asyncio.to_thread when needed.
    """

    def __init__(
        self,
        *,
        local_root: Path,
        repo_slug: str,
        installation_id: int,
        app_id: str,
        private_key_pem: str,
    ) -> None:
        self._root = Path(local_root).resolve()
        self._repo_slug = repo_slug
        self._installation_id = installation_id
        self._app_id = app_id
        self._private_key = private_key_pem
        self._local = LocalBackend(local_root)
        self._ensure_clone()

    # --- internal helpers ---

    def _token(self) -> str:
        return get_installation_token(self._app_id, self._private_key, self._installation_id)

    def _remote_url(self) -> str:
        return f"https://x-access-token:{self._token()}@github.com/{self._repo_slug}.git"

    def _git(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self._root, capture_output=True, text=True
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {args[0]!r} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def _ensure_clone(self) -> None:
        if (self._root / ".git").exists():
            return
        self._root.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", self._remote_url(), "."],
            cwd=self._root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Empty repo — init locally then add remote
            subprocess.run(["git", "init"], cwd=self._root, check=True, capture_output=True)
            subprocess.run(
                ["git", "remote", "add", "origin", self._remote_url()],
                cwd=self._root,
                check=True,
                capture_output=True,
            )
        self._git("config", "user.name", "Conexus")
        self._git("config", "user.email", "noreply@conexus.ai")

    def _refresh_remote(self) -> None:
        self._git("remote", "set-url", "origin", self._remote_url())

    def _pull(self) -> None:
        self._refresh_remote()
        self._git("pull", "--ff-only", "origin", "main", check=False)

    def _commit_push(self, message: str) -> None:
        self._git("add", "-A")
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=self._root, capture_output=True
        )
        if diff.returncode == 0:
            return  # nothing staged
        self._git("commit", "-m", message)
        self._refresh_remote()
        self._git("push", "origin", "main")

    # --- WikiBackend interface ---

    def read(self, path: str) -> str:
        self._pull()
        return self._local.read(path)

    def write(self, path: str, content: str) -> None:
        self._pull()
        self._local.write(path, content)
        self._commit_push(f"chore: update {path}")

    def list(self, folder: str = "") -> list[str]:
        self._pull()
        return self._local.list(folder)

    def search(self, query: str) -> list[dict]:
        self._pull()
        return self._local.search(query)

    def exists(self, path: str) -> bool:
        return self._local.exists(path)

    def delete(self, path: str) -> None:
        self._pull()
        self._local.delete(path)  # raises FileNotFoundError if missing
        self._commit_push(f"chore: delete {path}")
