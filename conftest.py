"""Pytest bootstrap: put the repo root on sys.path.

The plugin's runtime imports are package-relative (rooted at the plugin folder
StreamController loads), but for tests we import the pure `backend` package
directly, so the repo root must be importable.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
