"""Make project helpers importable without writing into the source checkout."""
from pathlib import Path
import sys


sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
