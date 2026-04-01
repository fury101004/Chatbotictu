"""Compatibility wrapper for the app data cleaning command."""

from app.data.clean_raw import main


if __name__ == "__main__":
    raise SystemExit(main())
