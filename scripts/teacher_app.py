"""Entry point of the one-file teacher app (PyInstaller): `codezoo teacher`.

Build it with scripts/build_teacher_app.py; the app holds Python, the engine and the web
client, so a school laptop needs nothing installed.
"""

import sys

from mse_codezoo.cli import main

if __name__ == "__main__":
    sys.exit(main(["teacher", *sys.argv[1:]]))
