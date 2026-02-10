# LLM-as-a-Judge — Especificação de Formatos

**Versão:** 1.0
**Data:** 2026-02-09

---

## 1. Visão Geral

Este documento define os formatos de entrada, saída e gabarito do componente de avaliação de qualidade (LLM-as-a-Judge) do experimento de comparação energética.

O sistema recebe arquivos de respostas geradas por LLMs, compara cada resposta contra um gabarito estruturado e produz um relatório de avaliação com veredictos binários (SUCESSO/FALHA).

---

## 2. Estrutura de Diretórios

```
llm-as-a-judge/
├── SPEC.md                 # Este documento
├── gabarito.json           # Critérios de avaliação (100 tarefas)
├── prompt_juiz.md          # Prompt para o LLM-juiz (trigger Copilot)
├── respostas/              # Arquivos de entrada (quantidade variável)
│   ├── exemplo.json
│   └── ...
└── resultados/             # Outputs gerados pelo juiz
    └── eval_YYYY-MM-DD_HHMMSS.json
```

---

## 3. Formato de Entrada: Arquivo de Respostas

Cada arquivo representa uma run completa (ou parcial) de um LLM respondendo às tarefas do experimento.

### 3.1 Estrutura

```json
{
  "metadata": {
    "id": "string obrigatório — identificador único da run",
    "model": "string opcional — nome do modelo",
    "timestamp": "string opcional — ISO 8601",
    "notes": "string opcional — observações livres"
  },
  "responses": {
    "L1_01": "C",
    "L1_02": "C",
    "L3_01": "Sim, é viável. A linha 2 estará operacional em julho...",
    "L4_01": "É sustentável, mas com sacrifício financeiro..."
  }
}
```

### 3.2 Regras

| Campo | Obrigatório | Descrição |
|---|---|---|
| `metadata.id` | Sim | Identificador único. Formato livre. Exemplos: `opus4_run_01`, `gemini25pro_mono_03` |
| `metadata.model` | Não | Nome do modelo usado |
| `metadata.timestamp` | Não | Quando a run foi executada |
| `metadata.notes` | Não | Campo livre para anotações |
| `responses` | Sim | Dicionário `task_id → resposta` |

### 3.3 Formato das Respostas por Nível

| Nível | Formato da resposta | Exemplo |
|---|---|---|
| **L1** (múltipla escolha) | Apenas a letra da alternativa: `A`, `B`, `C` ou `D` | `"L1_01": "C"` |
| **L2** (agregação) | Texto livre | `"L2_01": "A empresa endereça o risco de seca..."` |
| **L3** (multi-hop) | Texto livre | `"L3_01": "Sim, é viável. A linha 2..."` |
| **L4** (estratégico) | Texto livre | `"L4_01": "É sustentável, mas..."` |

### 3.4 Arquivos Parciais

O arquivo **não precisa** conter todas as 100 tarefas. O sistema avalia apenas as tarefas presentes. Tarefas ausentes são ignoradas (não contam como falha nem como sucesso).

### 3.5 Restrições

- Chaves de `responses` devem seguir o padrão `L{nível}_{número}` (ex: `L1_01`, `L3_25`, `L4_12`).
- Respostas de L1 devem conter **apenas** uma letra (`A`, `B`, `C` ou `D`). Qualquer outro conteúdo será tratado como resposta inválida.
- Respostas de L2-L4 são texto livre sem limite de tamanho.
- Encoding: UTF-8.

---

## 4. Formato do Gabarito

Arquivo `gabarito.json` na raiz do projeto.

### 4.1 Estrutura

```json
{
  "L1_01": {
    "level": 1,
    "question": "Qual é o custo médio de coleta de matéria-prima por tonelada?",
    "answer": "C",
    "answer_value": "R$180/ton",
    "source": "Doc 4 — Seção 2, Logística de coleta"
  },
  "L2_01": {
    "level": 2,
    "question": "Como a empresa endereça o risco de seca nas diferentes áreas do planejamento?",
    "criteria": [
      "Menciona fundo de irrigação emergencial R$80K (Doc 4, R1)",
      "Menciona contingência de R$150K para eventos climáticos (Doc 2, Orçamento)",
      "Menciona OKR de diversificação de frutas por resiliência climática (Doc 1, OKR 4)"
    ],
    "source": "Doc 1 (OKR 4), Doc 2 (Orçamento), Doc 4 (Mapa de riscos R1)"
  },
  "L3_01": {
    "level": 3,
    "question": "A meta anual de processamento de polpa para 2026 é viável considerando o cronograma de instalação da linha 2?",
    "criteria": [
      "Identifica meta: 400 ton de polpa em 2026",
      "Identifica que a linha 2 opera plenamente a partir de julho/2026, e a linha 1 tem capacidade de 300 ton/ano",
      "Conclui que a meta é viável: linha 1 opera jan-jun (~150 ton) + capacidade combinada jul-dez (~400 ton), totalizando ~550 ton potenciais vs 400 ton de meta"
    ],
    "source": "Doc 2 (Projeção receita Seção 3), Doc 4 (Cronograma linha 2 Seção 3, Capacidade Seção 1)"
  },
  "L4_01": {
    "level": 4,
    "question": "A meta estratégica de priorização do mercado interno é financeiramente sustentável no curto prazo, considerando as diferenças de margem entre canais?",
    "criteria": [
      "Identifica meta: mínimo 70% mercado interno (Doc 1, OKR 1)",
      "Identifica diferença de margens: 28% interno vs 58% exportação (Doc 2)",
      "Identifica cenários de break-even: 70/30 → 2028, 60/40 → 2026 (Doc 2)",
      "Conclui que a meta é sustentável (margem líquida positiva) mas atrasa o retorno do investimento em ~2 anos"
    ],
    "source": "Doc 1 (OKR 1 KR2 Seção 4), Doc 2 (Margens Seção 1, Break-even Seção 6)"
  }
}
```

### 4.2 Campos por Nível

| Nível | Campos obrigatórios |
|---|---|
| **L1** | `level`, `question`, `answer` (letra), `answer_value` (valor legível) |
| **L2–L4** | `level`, `question`, `criteria` (lista de strings) |

O campo `source` é informativo (documenta a origem no contexto) e não é usado na avaliação.

---

## 5. Avaliação

### 5.1 Nível 1 — Verificação Automática

Comparação exata de string (case-insensitive): resposta == gabarito.answer.

Não requer LLM. Pode ser feita por script ou pelo juiz — o resultado é o mesmo.

### 5.2 Níveis 2–4 — LLM-as-Judge

O juiz recebe a pergunta, os critérios do gabarito e a resposta gerada. Avalia se **todos** os critérios foram atendidos.

- **SUCESSO (1):** todos os critérios presentes na resposta, sem erros factuais.
- **FALHA (0):** qualquer critério ausente ou erro factual.

### 5.3 Tolerâncias

- Valores numéricos: tolerância de ±5% (ex: "R$170/ton" é aceitável se o gabarito diz "R$180/ton" — mas "R$120/ton" não é).
- Terminologia: sinônimos são aceitos (ex: "lucro operacional" = "EBITDA" no contexto).
- Informação extra: conteúdo adicional correto não penaliza. Conteúdo adicional **incorreto** (alucinação) resulta em FALHA.

---

## 6. Formato de Saída: Relatório de Avaliação

Gerado em `resultados/eval_YYYY-MM-DD_HHMMSS.json`.

### 6.1 Estrutura

```json
{
  "eval_timestamp": "2026-02-09T16:00:00",
  "gabarito_version": "1.0",
  "files_evaluated": ["opus4_run_01", "gemini25pro_run_01"],
  "results": {
    "opus4_run_01": {
      "tasks": {
        "L1_01": 1,
        "L1_02": 0,
        "L3_01": 1,
        "L4_01": 0
      },
      "summary": {
        "L1": { "evaluated": 25, "success": 20, "rate": 0.80 },
        "L2": { "evaluated": 25, "success": 18, "rate": 0.72 },
        "L3": { "evaluated": 25, "success": 15, "rate": 0.60 },
        "L4": { "evaluated": 25, "success": 10, "rate": 0.40 },
        "overall": { "evaluated": 100, "success": 63, "rate": 0.63 }
      }
    },
    "gemini25pro_run_01": {
      "tasks": { "..." : "..." },
      "summary": { "..." : "..." }
    }
  }
}
```

### 6.2 Campos

| Campo | Descrição |
|---|---|
| `eval_timestamp` | Quando a avaliação foi executada |
| `files_evaluated` | Lista dos `metadata.id` avaliados nesta run |
| `results[id].tasks` | Dicionário `task_id → 1 (sucesso) ou 0 (falha)` |
| `results[id].summary` | Agregação por nível: quantas avaliadas, quantas sucesso, taxa |
| `results[id].summary.overall` | Agregação total (todos os níveis presentes) |

### 6.3 Observações

- Apenas tarefas presentes no arquivo de respostas aparecem em `tasks`.
- `summary` agrupa apenas os níveis que tinham tarefas no arquivo.
- Se o arquivo tem só L3+L4, `summary` terá apenas `L3`, `L4` e `overall`.

---

## 7. Evolução Planejada

Funcionalidades para versões futuras (não implementadas na v1):

1. **Justificativa do juiz:** campo `justification` por tarefa explicando o veredicto.
2. **Módulo API:** avaliação via API (Claude/GPT) em batch, sem depender do VSCode.
3. **Comparativo entre condições:** agrupamento automático mono vs. multi com estatísticas.
4. **Exportação CSV/DataFrame:** conversão do JSON de resultados para análise em pandas/R.

---

## 8. Exemplo Completo

### Entrada (`respostas/opus4_run_01.json`)

```json
{
  "metadata": {
    "id": "opus4_run_01",
    "model": "Claude Opus 4",
    "timestamp": "2026-02-09T09:28:45"
  },
  "responses": {
    "L3_01": "Sim, é viável. A meta é de 400 ton de polpa no ano. A linha 1 tem capacidade de 300 ton/ano e a linha 2 (500 ton/ano) só estará operacional em julho/2026. Portanto, de janeiro a junho, a capacidade disponível é de 300 ton/ano (≈150 ton no semestre). De julho a dezembro, com as duas linhas, a capacidade é de 800 ton/ano (≈400 ton no semestre). Total disponível: ~550 ton, o que comporta os 400 ton.",
    "L3_02": "Sim. Os contratos PNAE exigem certificação orgânica vigente e SIF. A certificação orgânica IBD vence em março/2026, e o novo certificado só está previsto para abril/2026. Há, portanto, um gap de aproximadamente 1 mês."
  }
}
```

### Saída (`resultados/eval_2026-02-09_160000.json`)

```json
{
  "eval_timestamp": "2026-02-09T16:00:00",
  "gabarito_version": "1.0",
  "files_evaluated": ["opus4_run_01"],
  "results": {
    "opus4_run_01": {
      "tasks": {
        "L3_01": 1,
        "L3_02": 1
      },
      "summary": {
        "L3": { "evaluated": 2, "success": 2, "rate": 1.00 },
        "overall": { "evaluated": 2, "success": 2, "rate": 1.00 }
      }
    }
  }
}
```