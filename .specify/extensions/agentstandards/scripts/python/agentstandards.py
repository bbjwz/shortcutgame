# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.28,<1",
#   "pydantic>=2.10,<3",
#   "PyYAML>=6.0,<7",
# ]
# ///
from __future__ import annotations

import os
import shutil
import sys
from importlib.util import find_spec
from pathlib import Path

if any(find_spec(package) is None for package in ("httpx", "pydantic", "yaml")):
    uv_executable = shutil.which("uv")
    if not uv_executable:
        raise RuntimeError("uv is required to install the Agentstandards runtime dependencies")
    os.execv(  # noqa: S606 - replace this dependency-bootstrap process without a shell
        uv_executable,
        [uv_executable, "run", "--script", str(Path(__file__).resolve()), *sys.argv[1:]],
    )

extension_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(extension_root / "runtime"))

from agentstandards.cli import main  # noqa: E402

raise SystemExit(main())
