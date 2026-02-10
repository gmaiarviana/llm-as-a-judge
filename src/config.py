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

# --- OpenAI API ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("ERRO: OPENAI_API_KEY não encontrada no .env")
    sys.exit(1)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# --- Constantes de modo ---
MODE_FLEX = "flex"
MODE_BATCH = "batch"
MODE_STANDARD = "standard"

# --- Tabela de preços (USD por 1M tokens) ---
PRICING = {
    "gpt-4o-mini": {
        "standard": {"input": 0.15, "output": 0.60},
        "batch":    {"input": 0.075, "output": 0.30},
        "flex":     {"input": 0.075, "output": 0.30},
    },
    "gpt-4o": {
        "standard": {"input": 2.50, "output": 10.00},
        "batch":    {"input": 1.25, "output": 5.00},
        "flex":     {"input": 1.25, "output": 5.00},
    },
}

# --- Câmbio ---
USD_TO_BRL = 5.20  # Atualizar manualmente quando necessário

# --- Batch API config ---
BATCH_POLL_INTERVAL = 30  # segundos entre polls
BATCH_COMPLETION_WINDOW = "24h"
BATCH_ENDPOINT = "/v1/chat/completions"

# --- Caminhos (relativos à raiz do projeto) ---
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"

GABARITO_PATH = DATA_DIR / "gabarito.json"
RESPOSTAS_DIR = DATA_DIR / "respostas"
RESULTADOS_DIR = DATA_DIR / "resultados"
PROMPT_PATH = DATA_DIR / "prompt_juiz.txt"


# --- Funções utilitárias ---
def calculate_cost(model: str, mode: str, prompt_tokens: int, completion_tokens: int) -> dict:
    """Calcula custo em USD e BRL baseado no modelo, modo e tokens usados."""
    if model not in PRICING:
        print(f"WARNING: Modelo '{model}' não encontrado na tabela de preços. Custo = 0.0")
        return {"usd": 0.0, "brl": 0.0}
    
    if mode not in PRICING[model]:
        print(f"WARNING: Modo '{mode}' não encontrado para modelo '{model}'. Custo = 0.0")
        return {"usd": 0.0, "brl": 0.0}
    
    pricing = PRICING[model][mode]
    cost_input = (prompt_tokens / 1_000_000) * pricing["input"]
    cost_output = (completion_tokens / 1_000_000) * pricing["output"]
    cost_usd = cost_input + cost_output

    return {
        "usd": cost_usd,
        "brl": round(cost_usd * USD_TO_BRL, 2),
    }