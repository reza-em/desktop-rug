#!/usr/bin/env python3
"""Test helper: an ordinary application window, to verify the rug stays below it."""
import sys
from PySide6.QtWidgets import QApplication, QLabel
app = QApplication(sys.argv)
l = QLabel("  A normal app window (rug must stay below this)  ")
l.setStyleSheet("background:#f4f4f4; font-size:18px; border:1px solid #888;")
l.setWindowTitle("Normal window")
l.resize(420, 160)
l.move(int(sys.argv[1]) if len(sys.argv) > 1 else 60, int(sys.argv[2]) if len(sys.argv) > 2 else 520)
l.show()
app.exec()
