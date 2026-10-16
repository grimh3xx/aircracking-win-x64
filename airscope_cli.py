#!/usr/bin/env python3
"""Entry point pro PyInstaller (evita o problema de import relativo do __main__).

    python -m PyInstaller --onefile --name airscope airscope_cli.py
"""
import sys

from airscope.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
