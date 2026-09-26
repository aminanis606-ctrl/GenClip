import os
from pathlib import Path

ROOT = Path.home() / "clipper-core"
TEMP = ROOT / "temp"
OUTPUT = ROOT / "clips"

API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

TEMP.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)

if not API_KEY:
    raise RuntimeError("GROQ_API_KEY belum tersedia")
