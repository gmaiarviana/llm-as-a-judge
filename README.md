# LLM-as-a-Judge

Avaliador automatizado de respostas de LLMs. Compara respostas contra um gabarito estruturado usando OpenAI como juiz.

Parte do experimento de comparação energética da jornada PED.

## Provedor

- **OpenAI** (único): modelos configurados via `OPENAI_MODEL`

## Setup

```powershell
cd C:\Users\guilherme_viana\Desktop\WATAM\jornada-ped\llm-as-a-judge

# Criar e ativar ambiente virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt
```

Criar arquivo `.env` na raiz com:

```
OPENAI_API_KEY=sua_chave_aqui
OPENAI_MODEL=gpt-4o-mini
```

Para ativar o venv em sessões futuras:

```powershell
.venv\Scripts\Activate.ps1
```

## Modos de execução

- **flex** — síncrono, preço de batch, para testes
- **batch** — assíncrono via Batch API, para produção
- **standard** — síncrono, preço cheio, fallback

## Estrutura

```
llm-as-a-judge/
├── BACKLOG.md
├── README.md
├── requirements.txt
├── .env
├── .gitignore
│
├── src/
│   ├── __init__.py
│   ├── avaliar.py        # CLI + orquestração (entry point)
│   ├── config.py         # caminhos, constantes e preços
│   ├── evaluate.py       # lógica de avaliação
│   └── llm.py            # integração OpenAI (síncrona + batch)
│
├── data/
│   ├── gabarito.json
│   ├── prompt_juiz.txt
│   ├── respostas/        # input — arquivos de resposta (.json)
│   └── resultados/       # output — gerado pelo script
│
├── docs/
│   └── SPEC.md
│
└── tests/
```

## Uso

```powershell
# Teste rápido com 1 arquivo (flex)
python -m src.avaliar --modo flex --arquivo gemini25pro_run_01.json

# Produção com todos os arquivos (batch)
python -m src.avaliar --modo batch
```

## Output

O script gera dois arquivos em `data/resultados/`:

**`eval_YYYY-MM-DD_HHMMSS.json`** — veredictos, sumários e custo

```json
{
  "judge_mode": "standard",
  "files_evaluated": ["gemini25pro_run_01"],
  "cost_summary": {
    "model": "gpt-4o-mini",
    "mode": "standard",
    "total_prompt_tokens": 187000,
    "total_completion_tokens": 25000,
    "total_tokens": 212000,
    "api_calls": 50,
    "estimated_cost_usd": 0.021
  },
  "results": {
    "gemini25pro_run_01": {
      "tasks": { "L3_01": 0, "L3_02": 1, "...": "..." },
      "summary": {
        "L3": { "evaluated": 25, "success": 18, "rate": 0.72 },
        "L4": { "evaluated": 25, "success": 12, "rate": 0.48 },
        "overall": { "evaluated": 50, "success": 30, "rate": 0.60 }
      }
    }
  }
}
```

**`justificativas_YYYY-MM-DD.md`** — raciocínio do juiz

PASSes ficam em uma linha. FAILs recebem detalhamento critério-por-critério:

```
✓ L3_02 — all criteria met

### gemini25pro_run_01 — L3_01
- C1: ✓ — "meta de 400 ton de polpa"
- C2: ✓ — "linha 2 opera em julho"
- C3: ✗ — ausente
- **Veredicto: 0** (C3 ausente)
```

## Troubleshooting

**`❌ OPENAI_API_KEY não encontrada`** — Verifique se `.env` existe na raiz com:

```
OPENAI_API_KEY=sua_chave
OPENAI_MODEL=gpt-4o-mini
```

**`⚠ RateLimitError`** — Muitas requisições em pouco tempo. O script retenta automaticamente.

**`⚠ APITimeoutError`** — Timeout na OpenAI. Tente novamente ou use `--modo batch`.

**`⚠ InternalServerError` / `ServiceUnavailableError`** — Instabilidade temporária na OpenAI. Aguarde e rode novamente.

**`⚠ JSON inválido`** — O modelo retornou resposta mal formatada. O script retenta até 3x.