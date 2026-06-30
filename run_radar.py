"""Entry point for the packaged one-file app (PyInstaller builds from this).

Double-clicking the built `radar.exe` runs this: starts the local server and pops
the panel open in the browser. Same as `python -m radar`, but frozen.
"""
from radar.app import run

if __name__ == "__main__":
    run()
