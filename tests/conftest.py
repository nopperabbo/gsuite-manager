"""pytest configuration - ensure src/ is on path even when editable install fails.

This works around a Python pth-file quirk when project paths contain spaces.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Force Rich/Typer to disable color output in tests (prevents ANSI escape codes
# from breaking string assertions in CI where NO_COLOR may not propagate to
# CliRunner subprocesses).
os.environ.setdefault("NO_COLOR", "1")
os.environ.setdefault("TERM", "dumb")
