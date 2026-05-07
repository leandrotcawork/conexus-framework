"""Static list of identity tools, gated by identity.enabled."""
from __future__ import annotations

import inspect
from pathlib import Path

from conexus.core.identity.tools import IdentityTools
from conexus.web.admin.services.tools_inspector import ToolMethod, scan_tools_file


def list_identity_tools(*, enabled: bool) -> list[ToolMethod]:
    if not enabled:
        return []
    src_path = Path(inspect.getsourcefile(IdentityTools) or "")
    if not src_path.exists():
        return []
    return scan_tools_file(src_path)
