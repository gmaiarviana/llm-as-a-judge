# LLM-as-a-Judge

Avaliador automatizado de respostas de LLMs. Compara respostas contra um gabarito estruturado usando Gemini 2.0 Flash como juiz.

Parte do experimento de comparação energética da jornada PED.

## Setup

```powershell
cd C:\Users\guilherme_viana\Desktop\WATAM\jornada-ped\llm-as-a-judge

# Criar e ativar ambiente virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# Instalar dependências
pip install requests python-dotenv
```

Para ativar o venv em sessões futuras:

```powershell
.venv\Scripts\Activate.ps1
```

## Estrutura

```
llm-as-a-judge/
├── avaliar.py            # entry point (CLI + orquestração)
├── config.py             # caminhos e constantes
├── gemini.py             # wrapper da API Gemini
├── evaluate.py           # lógica de avaliação
├── gabarito.json         # critérios das 100 tarefas
├── prompt_juiz.txt       # system prompt do juiz (lido pelo script)
├── .env                  # GEMINI_API_KEY + GEMINI_MODEL
├── SPEC.md               # especificação de formatos
├── respostas/            # input — arquivos de resposta (.json)
└── resultados/           # output — gerado pelo script
```

## Uso

```powershell
# Testar com 1 arquivo (~6 min para 50 tasks)
python avaliar.py --arquivo gemini25pro_run_01.json

# Avaliar todos os arquivos em respostas/ (~30 min para 5 arquivos)
python avaliar.py
```

## Output

O script gera dois arquivos em `resultados/`:

**`eval_YYYY-MM-DD_HHMMSS.json`** — veredictos e sumários

```json
{
  "results": {
    "gemini25pro_run_01": {
      "tasks": { "L3_01": 0, "L3_02": 1, "..." : "..." },
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

## Avaliação por nível

| Nível | Método         | Custo API |
|-------|----------------|-----------|
| L1    | String match   | Zero      |
| L2-L4 | Gemini 2.0 Flash | 1 call/task |

L1 é avaliado localmente (comparação de letras). L2-L4 usam a API com ~4.5s entre chamadas (free tier: 15 req/min).

## Limites do free tier

| Recurso         | Limite         |
|-----------------|----------------|
| Requisições/min | 15             |
| Requisições/dia | 1.500          |
| Tokens/min      | 1.000.000      |

5 arquivos × 50 tasks = 250 tasks. Com L1 local, são ~190 chamadas API. Cabe em um dia.

## Troubleshooting

**`❌ GEMINI_API_KEY não encontrada`** — Verifique se `.env` existe na raiz com:

```
GEMINI_API_KEY=sua_chave
GEMINI_MODEL=gemini-2.0-flash
```

Para trocar de modelo, edite apenas o `.env`. Opções: `gemini-2.0-flash`, `gemini-2.0-flash-lite`.

**`⏳ Rate limited`** — O script aguarda 60s automaticamente e retenta.

**`⚠ JSON inválido`** — Gemini retornou resposta mal formatada. O script retenta até 3x.