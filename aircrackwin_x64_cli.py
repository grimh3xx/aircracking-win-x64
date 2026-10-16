#!/usr/bin/env python3
"""Entry point pro PyInstaller (evita o problema de import relativo do __main__).

    python -m PyInstaller --onefile --name aircrackwin-x64 aircrackwin_x64_cli.py
"""
import sys

from aircrackwin_x64.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
