"""Put the repo root on sys.path so `engine`, `spec`, and `server` import cleanly under pytest."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
