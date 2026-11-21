# The teacher app: a classroom hub without installing Python

`CodeZoo-Teacher.exe` (Windows) holds Python, the CodeZoo engine and the web client in one file. It runs the classroom hub: children join from tablets and laptops on the same network with a class code and a picture. See the README's "Classroom hub" section for what the hub does.

## Getting it

Download `CodeZoo-Teacher-windows` from the latest successful **Pilot builds** run on the project's GitHub Actions page (needs a GitHub login), and unzip it. (Or build it yourself: `uv run --with pyinstaller python scripts/build_teacher_app.py`.)

## First start: two warnings

The app is **not code-signed yet**, so Windows warns about it:

1. **"Windows protected your PC"** (SmartScreen): click **More info**, then **Run anyway**. This happens once per downloaded file.
2. **Windows Defender Firewall** asks whether CodeZoo may use networks: allow **Private networks**, so children's devices can reach the hub. Don't allow public networks.

On a school laptop where you can't do either, ask the school's IT for help, or use a laptop you manage.

## Using it

1. Double-click the app. A window opens and lists your classes, with "a new class or workshop" last.
2. Pick one, or make a new one (a name, then **workshop** for a one-off session or **class** for a group that meets regularly).
3. The window shows the address children open, the class code, and the teacher's address; the teacher's screen opens in your browser. Show the QR code from the teacher's screen on the projector.
4. Keep the window open while the class plays. Close it (or press Ctrl+C) to stop.

Classes and progress are kept in `%APPDATA%\CodeZoo\classes\` on this laptop. Nothing is sent to the internet.

macOS: not available yet (it needs Apple's notarisation). Install [uv](https://docs.astral.sh/uv/) and run `uvx --from git+https://github.com/mse11/mse-codezoo codezoo teacher` there for now.
