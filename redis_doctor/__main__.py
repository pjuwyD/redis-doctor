"""Entry point for `python -m redis_doctor` and the PyInstaller binary."""

from .cli import app

if __name__ == "__main__":
    app()
