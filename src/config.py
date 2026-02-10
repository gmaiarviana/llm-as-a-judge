"""Configuração central do avaliador."""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("Execute: pip install python-dotenv")
    sys.exit(1)

load_dotenv()

# --- API ---
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{MODEL}:generateContent?key={API_KEY}"
)

# --- Rate limit (free tier: 15 RPM) ---
RPM_LIMIT = 15
DELAY = 60 / RPM_LIMIT + 0.5  # ~4.5s entre chamadas

# --- Caminhos (relativos à raiz do projeto) ---
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

GABARITO_PATH = DATA_DIR / "gabarito.json"
RESPOSTAS_DIR = DATA_DIR / "respostas"
RESULTADOS_DIR = DATA_DIR / "resultados"
PROMPT_PATH = DATA_DIR / "prompt_juiz.txt"