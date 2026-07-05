"""RIE server package. Ensure the repo root is importable so `engine` resolves under uvicorn."""
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
