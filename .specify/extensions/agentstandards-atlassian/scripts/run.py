# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.28,<1",
#   "pydantic>=2.10,<3",
#   "PyYAML>=6,<7",
#   "markdown-it-py>=3,<5",
#   "lxml>=5,<7",
#   "Pillow>=11,<13",
#   "agentstandards @ git+https://github.com/bbjwz/agentstandards@da5a2f029bd318ac96ad5682430ca6fbf4a01640",
# ]
# ///
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agentstandards_atlassian.cli import main  # noqa: E402

raise SystemExit(main())
