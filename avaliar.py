#!/usr/bin/env python3
"""
avaliar.py — Entry point do avaliador LLM-as-Judge.
Uso: python avaliar.py [--arquivo nome.json]
"""

import json
import sys
import time
import argparse
from datetime import datetime

from config import (
    API_KEY,
    MODEL,
    DELAY,
    GABARITO_PATH,
    RESPOSTAS_DIR,
    RESULTADOS_DIR,
    PROMPT_PATH,
)
from evaluate import (
    load_gabarito,
    load_system_prompt,
    load_response_file,
    evaluate_file,
    compute_summary,
)


def main():
    parser = argparse.ArgumentParser(description="LLM-as-Judge — Avaliador")
    parser.add_argument(
        "--arquivo",
        type=str,
        default=None,
        help="Avaliar apenas um arquivo específico (nome do .json em respostas/)",
    )
    args = parser.parse_args()

    # --- Validações ---
    if not API_KEY:
        print("❌ GEMINI_API_KEY não encontrada no .env")
        sys.exit(1)

    for path, label in [
        (GABARITO_PATH, "gabarito.json"),
        (PROMPT_PATH, "prompt_juiz.txt"),
    ]:
        if not path.exists():
            print(f"❌ {label} não encontrado")
            sys.exit(1)

    if not RESPOSTAS_DIR.exists():
        print(f"❌ Pasta {RESPOSTAS_DIR}/ não encontrada")
        sys.exit(1)

    RESULTADOS_DIR.mkdir(exist_ok=True)

    # --- Carga ---
    system_prompt = load_system_prompt(PROMPT_PATH)
    gabarito, gab_version = load_gabarito(GABARITO_PATH)

    if args.arquivo:
        target = RESPOSTAS_DIR / args.arquivo
        if not target.exists():
            print(f"❌ {target} não encontrado")
            sys.exit(1)
        response_files = [target]
    else:
        response_files = sorted(RESPOSTAS_DIR.glob("*.json"))

    if not response_files:
        print(f"❌ Nenhum .json em {RESPOSTAS_DIR}/")
        sys.exit(1)

    # --- Estimativa ---
    sample = load_response_file(response_files[0])
    api_tasks = sum(1 for tid in sample["responses"] if not tid.startswith("L1_"))
    total_api_calls = api_tasks * len(response_files)
    est_minutes = (total_api_calls * DELAY) / 60

    print(f"\n{'=' * 60}")
    print(f"  LLM-as-Judge — Avaliador")
    print(f"{'=' * 60}")
    print(f"  Juiz:       {MODEL}")
    print(f"  Gabarito:   v{gab_version} ({len(gabarito)} tasks)")
    print(f"  Arquivos:   {len(response_files)}")
    print(f"  Chamadas:   ~{total_api_calls} API + L1 local")
    print(f"  Estimativa: ~{est_minutes:.0f} min")
    print(f"{'=' * 60}\n")

    # --- Avaliação ---
    all_results = {}
    all_justificativas = []
    files_evaluated = []
    total_calls = 0
    start_time = time.time()

    for file_path in response_files:
        print(f"\n{'─' * 50}")
        print(f"📄 {file_path.name}")
        print(f"{'─' * 50}")

        file_id, tasks, justificativas, api_calls = evaluate_file(
            file_path, gabarito, system_prompt
        )
        files_evaluated.append(file_id)
        total_calls += api_calls

        summary = compute_summary(tasks)
        all_results[file_id] = {"tasks": tasks, "summary": summary}

        all_justificativas.append(f"\n## {file_id}\n")
        all_justificativas.extend(justificativas)

        print(f"\n  📊 {file_id}:")
        for level, stats in summary.items():
            pct = f"{stats['rate']:.0%}"
            print(f"     {level}: {stats['success']}/{stats['evaluated']} ({pct})")

    elapsed = time.time() - start_time

    # --- Salvar outputs ---
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S")
    file_ts = now.strftime("%Y-%m-%d_%H%M%S")

    # JSON
    eval_output = {
        "eval_timestamp": timestamp,
        "gabarito_version": gab_version,
        "judge_model": MODEL,
        "files_evaluated": files_evaluated,
        "results": all_results,
    }
    eval_path = RESULTADOS_DIR / f"eval_{file_ts}.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(eval_output, f, ensure_ascii=False, indent=2)

    # Markdown
    just_path = RESULTADOS_DIR / f"justificativas_{now.strftime('%Y-%m-%d')}.md"
    with open(just_path, "w", encoding="utf-8") as f:
        f.write(f"# Justificativas — Avaliação {now.strftime('%Y-%m-%d')}\n\n")
        f.write(f"Juiz: {MODEL} | Gabarito v{gab_version}\n")
        f.write(f"Arquivos: {len(files_evaluated)} | ")
        f.write(f"Chamadas API: {total_calls} | ")
        f.write(f"Tempo: {elapsed / 60:.1f} min\n")
        f.write("\n".join(all_justificativas))
        f.write("\n")

    print(f"\n{'=' * 60}")
    print(f"  ✅ Avaliação concluída!")
    print(f"     Chamadas API: {total_calls}")
    print(f"     Tempo total:  {elapsed / 60:.1f} min")
    print(f"     📄 {eval_path}")
    print(f"     📄 {just_path}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()