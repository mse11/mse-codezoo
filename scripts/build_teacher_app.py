"""Build the one-file teacher app (phase 6) with PyInstaller.

    uv run --with pyinstaller python scripts/build_teacher_app.py

Writes dist/CodeZoo-Teacher(.exe). It is not code-signed yet: Windows shows a SmartScreen
warning the first time ("More info", then "Run anyway"); see docs/pilot/teacher-app.md.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]

subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",  # the window shows the class code and the addresses
        "--name",
        "CodeZoo-Teacher",
        "--collect-data",
        "mse_codezoo",  # levels, animals, translations and the web client
        "--collect-submodules",
        "mse_codezoo",
        "--noconfirm",
        str(ROOT / "scripts" / "teacher_app.py"),
    ],
    cwd=ROOT,
    check=True,
)
