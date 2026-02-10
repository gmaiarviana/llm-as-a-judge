# BACKLOG — LLM-as-a-Judge

Melhorias futuras e débitos técnicos do sistema de avaliação.
Itens aqui foram discutidos e adiados por decisão explícita.

## Qualidade do Juiz

- [ ] **Majority vote (3x):** rodar 3 avaliações por task, veredicto = maioria. Triplica custo mas estabiliza resultado. Prioridade alta se variância com temperature=0 for > 5pp entre runs.
- [ ] **Modelo mais capaz:** trocar de `gpt-4o-mini` para `gpt-4o` se qualidade insuficiente. Custo sobe ~6x mas ainda é baixo (~$0.50/run de 250 tasks).
- [ ] **Multi-model jury:** avaliar com 2+ modelos diferentes (ex: gpt-4o + claude sonnet). Se concordância > 90%, confiança alta.
- [ ] **Calibração contra humanos:** Kappa de Fleiss com 3 avaliadores em amostra de 50-100 tasks (previsto na metodologia experimental, seção 6.6).

## Escala e Automação

- [ ] **Retry automático para batch failures:** ler error_file do batch, resubmeter apenas tasks falhadas.
- [ ] **Comparativo entre runs:** script que compara 2+ JSONs de resultado e mostra diff por task (útil para medir variância do juiz).
- [ ] **Exportação CSV/DataFrame:** converter JSON de resultados para análise em pandas/R.

## Observações

**Variância do juiz (Gemini Flash):** observamos 26pp de diferença entre duas avaliações das mesmas respostas com Gemini 2.0 Flash (48% vs 74%). Causa provável: sem temperature=0 e modelo leve. A migração para OpenAI com temperature=0 deve reduzir. Se persistir, implementar majority vote.

**Custo estimado do experimento completo:** 4200 respostas em batch com gpt-4o-mini ≈ $0.80. Com gpt-4o ≈ $5. Com majority vote 3x: multiplicar por 3.
