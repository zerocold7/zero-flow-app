"""
Run the reader on its own:  python -m reader   (or Launch_Reader.bat)

The engine's other half runs separately via `local_flow.py`. To run both in one
process and one console window, use `zero_flow.py` instead.
"""
import logging
import traceback

from reader import app

if __name__ == "__main__":
    try:
        app.main()
    except Exception:
        logging.critical(f"Fatal reader crash: {traceback.format_exc()}")
