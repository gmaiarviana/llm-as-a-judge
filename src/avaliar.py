#!/usr/bin/env python3
"""
avaliar.py — Entry point do avaliador LLM-as-Judge com 3 modos de execução.
Uso:
    python -m src.avaliar --modo flex [--arquivo nome.json]
    python -m src.avaliar --modo batch [--arquivo nome.json]
    python -m src.avaliar --modo standard [--arquivo nome.json]
"""

import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

from .config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    GABARITO_PATH,
    RESPOSTAS_DIR,
    RESULTADOS_DIR,
    PROMPT_PATH,
    MODE_FLEX,
    MODE_BATCH,
    MODE_STANDARD,
    DATA_DIR,
    calculate_cost,
    BATCH_POLL_INTERVAL,
    USD_TO_BRL,
)
from .evaluate import (
    load_gabarito,
    load_system_prompt,
    load_response_file,
    evaluate_file,
    compute_summary,
)
from .llm import (
    upload_batch_file,
    create_batch,
    poll_batch,
    download_batch_results,
)


# ============================================================
# BATCH MODE HELPERS
# ============================================================

def prepare_batch(
    response_files: list[Path],
    gabarito: dict,
    system_prompt: str,
) -> tuple[Path, Path, dict]:
    """
    Prepara batch: gera JSONL + avalia L1 localmente.
    
    Returns:
        (jsonl_path, l1_results_path, l1_results_dict)
    """
    from .llm import build_batch_line
    from .evaluate import build_user_prompt, evaluate_l1
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    jsonl_path = DATA_DIR / f"batch_{timestamp}.jsonl"
    l1_path = DATA_DIR / f"batch_l1_{timestamp}.json"
    
    batch_lines = []
    l1_results = {}
    
    print("\n📝 Preparando batch...")
    
    for file_path in response_files:
        data = load_response_file(file_path)
        file_id = data["metadata"]["id"]
        responses = data["responses"]
        
        l1_results[file_id] = {}
        
        for task_id, response_text in responses.items():
            if task_id not in gabarito:
                continue
            
            gab = gabarito[task_id]
            level = gab["level"]
            
            # L1: avaliar localmente
            if level == 1:
                verdict = evaluate_l1(response_text, gab["answer"])
                l1_results[file_id][task_id] = verdict
                print(f"  ✓ {file_id} — {task_id}: L1 local")
            
            # L2-L4: adicionar ao batch
            else:
                user_prompt = build_user_prompt(task_id, gab, response_text)
                custom_id = f"{file_id}::{task_id}"
                line = build_batch_line(custom_id, system_prompt, user_prompt)
                batch_lines.append(line)
    
    # Salvar JSONL
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.write("\n".join(batch_lines))
    
    # Salvar L1 results
    with open(l1_path, "w", encoding="utf-8") as f:
        json.dump(l1_results, f, indent=2)
    
    print(f"  ✅ {len(batch_lines)} tasks no batch")
    print(f"  ✅ {sum(len(tasks) for tasks in l1_results.values())} tasks L1 locais")
    print(f"  📄 {jsonl_path}")
    print(f"  📄 {l1_path}")
    
    return jsonl_path, l1_path, l1_results


def process_batch_results(
    batch_results: list[dict],
    l1_results: dict,
    gabarito: dict,
) -> tuple[dict, list, dict]:
    """
    Processa resultados do batch + L1 locais.
    
    Args:
        batch_results: Lista de dicts com custom_id, result, usage
        l1_results: Dict {file_id: {task_id: verdict}}
        gabarito: Dict do gabarito
    
    Returns:
        (all_results, all_justificativas, cost_info)
    """
    # Organizar batch results por arquivo
    batch_by_file = {}
    total_prompt_tokens = 0
    total_completion_tokens = 0
    api_calls = 0
    
    for item in batch_results:
        custom_id = item["custom_id"]
        file_id, task_id = custom_id.split("::")
        
        if file_id not in batch_by_file:
            batch_by_file[file_id] = {}
        
        batch_by_file[file_id][task_id] = item["result"]
        
        # Acumular tokens
        total_prompt_tokens += item["usage"]["prompt_tokens"]
        total_completion_tokens += item["usage"]["completion_tokens"]
        api_calls += 1
    
    # Combinar L1 + batch results
    all_results = {}
    all_justificativas = []
    
    # Processar cada arquivo
    for file_id in l1_results.keys():
        tasks = {}
        justificativas = []
        
        # Adicionar L1 results
        for task_id, verdict in l1_results[file_id].items():
            tasks[task_id] = verdict
            gab = gabarito[task_id]
            r = load_response_file(RESPOSTAS_DIR / f"{file_id}.json")["responses"][task_id].strip().upper()
            c = gab["answer"].strip().upper()
            
            if verdict:
                justificativas.append(f"✓ {task_id} — '{r}' = '{c}'")
            else:
                justificativas.append(f"✗ {task_id} — '{r}' ≠ '{c}'")
        
        # Adicionar batch results
        if file_id in batch_by_file:
            for task_id, result in batch_by_file[file_id].items():
                if result is None:
                    tasks[task_id] = 0
                    justificativas.append(
                        f"\n### {file_id} — {task_id}\n"
                        f"- ERRO: falha no batch\n"
                        f"- **Veredicto: 0** (erro)\n"
                    )
                    continue
                
                verdict = result.get("verdict", 0)
                tasks[task_id] = verdict
                
                if verdict == 1:
                    justificativas.append(f"✓ {task_id} — all criteria met")
                else:
                    lines = [f"\n### {file_id} — {task_id}"]
                    for c in result.get("criteria", []):
                        sym = "✓" if c.get("met") else "✗"
                        evidence = c.get("evidence", "?")
                        lines.append(f"- C{c.get('id', '?')}: {sym} — {evidence}")
                    
                    hall = result.get("hallucination")
                    if hall:
                        lines.append(f"- Alucinação: {hall}")
                    
                    reason = result.get("fail_reason", "critério ausente")
                    lines.append(f"- **Veredicto: 0** ({reason})")
                    justificativas.append("\n".join(lines))
        
        # Computar sumário
        summary = compute_summary(tasks)
        all_results[file_id] = {"tasks": tasks, "summary": summary}
        
        all_justificativas.append(f"\n## {file_id}\n")
        all_justificativas.extend(justificativas)
        
        # Print sumário
        print(f"\n  📊 {file_id}:")
        for level, stats in summary.items():
            pct = f"{stats['rate']:.0%}"
            print(f"     {level}: {stats['success']}/{stats['evaluated']} ({pct})")
    
    cost_info = {
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "api_calls": api_calls,
    }
    
    return all_results, all_justificativas, cost_info


# ============================================================
# MODO FLEX / STANDARD
# ============================================================

def run_flex_or_standard_mode(
    mode: str,
    response_files: list[Path],
    gabarito: dict,
    gab_version: str,
    system_prompt: str,
) -> tuple[dict, list, dict, float]:
    """
    Executa avaliação em modo flex ou standard.
    
    Returns:
        (all_results, all_justificativas, cost_info, elapsed_time)
    """
    service_tier = "flex" if mode == MODE_FLEX else None
    
    all_results = {}
    all_justificativas = []
    files_evaluated = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    api_calls = 0
    start_time = time.time()
    
    for file_path in response_files:
        print(f"\n{'─' * 50}")
        print(f"📄 {file_path.name}")
        print(f"{'─' * 50}")
        
        file_id, tasks, justificativas, token_usage = evaluate_file(
            file_path, gabarito, system_prompt, service_tier
        )
        files_evaluated.append(file_id)
        
        # Acumular tokens e calls
        total_prompt_tokens += token_usage["prompt_tokens"]
        total_completion_tokens += token_usage["completion_tokens"]
        api_calls += token_usage["api_calls"]
        
        summary = compute_summary(tasks)
        all_results[file_id] = {"tasks": tasks, "summary": summary}
        
        all_justificativas.append(f"\n## {file_id}\n")
        all_justificativas.extend(justificativas)
        
        print(f"\n  📊 {file_id}:")
        for level, stats in summary.items():
            pct = f"{stats['rate']:.0%}"
            print(f"     {level}: {stats['success']}/{stats['evaluated']} ({pct})")
    
    elapsed = time.time() - start_time
    
    cost_info = {
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "api_calls": api_calls,
    }
    
    return all_results, all_justificativas, cost_info, elapsed


# ============================================================
# MODO BATCH
# ============================================================

def run_batch_mode(
    response_files: list[Path],
    gabarito: dict,
    gab_version: str,
    system_prompt: str,
) -> tuple[dict, list, dict, float, Path, Path]:
    """
    Executa avaliação em modo batch.
    
    Returns:
        (all_results, all_justificativas, cost_info, elapsed_time, jsonl_path, l1_path)
    """
    start_time = time.time()
    
    # 1. Preparar batch (gerar JSONL + avaliar L1 localmente)
    jsonl_path, l1_path, l1_results = prepare_batch(
        response_files, gabarito, system_prompt
    )
    
    # 2. Upload
    print("\n📤 Enviando batch...")
    file_id = upload_batch_file(str(jsonl_path))
    
    # 3. Criar batch
    print("\n🚀 Criando batch...")
    batch_id = create_batch(file_id)
    
    # 4. Poll até completar
    print(f"\n⏳ Aguardando conclusão (polling a cada {BATCH_POLL_INTERVAL}s)...")
    batch = poll_batch(batch_id, interval=BATCH_POLL_INTERVAL)
    
    # 5. Download resultados
    print("\n📥 Baixando resultados...")
    output_file_id = batch.output_file_id
    batch_results = download_batch_results(output_file_id)
    
    # 6. Processar resultados
    print("\n📊 Processando resultados...")
    all_results, all_justificativas, cost_info = process_batch_results(
        batch_results, l1_results, gabarito
    )
    
    elapsed = time.time() - start_time
    
    return all_results, all_justificativas, cost_info, elapsed, jsonl_path, l1_path


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="LLM-as-Judge — Avaliador com suporte a flex, batch e standard"
    )
    parser.add_argument(
        "--modo",
        type=str,
        required=True,
        choices=[MODE_FLEX, MODE_BATCH, MODE_STANDARD],
        help="Modo de execução: flex, batch ou standard",
    )
    parser.add_argument(
        "--arquivo",
        type=str,
        default=None,
        help="Avaliar apenas um arquivo específico (nome do .json em respostas/)",
    )
    args = parser.parse_args()
    
    mode = args.modo
    
    # --- Validações ---
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY não encontrada no .env")
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
    
    # --- Header ---
    print(f"\n{'=' * 60}")
    print(f"  LLM-as-Judge — Avaliador")
    print(f"{'=' * 60}")
    print(f"  Modo:       {mode}")
    print(f"  Juiz:       {OPENAI_MODEL}")
    print(f"  Gabarito:   v{gab_version} ({len(gabarito)} tasks)")
    print(f"  Arquivos:   {len(response_files)}")
    print(f"{'=' * 60}")
    
    # --- Executar avaliação ---
    if mode == MODE_BATCH:
        all_results, all_justificativas, cost_info, elapsed, jsonl_path, l1_path = run_batch_mode(
            response_files, gabarito, gab_version, system_prompt
        )
    else:
        all_results, all_justificativas, cost_info, elapsed = run_flex_or_standard_mode(
            mode, response_files, gabarito, gab_version, system_prompt
        )
        jsonl_path = None
        l1_path = None
    
    # --- Calcular custo ---
    total_prompt_tokens = cost_info["total_prompt_tokens"]
    total_completion_tokens = cost_info["total_completion_tokens"]
    total_tokens = total_prompt_tokens + total_completion_tokens
    api_calls = cost_info["api_calls"]
    
    cost_mode = "batch" if mode == MODE_BATCH else "standard"
    estimated_cost = calculate_cost(
        OPENAI_MODEL, cost_mode, total_prompt_tokens, total_completion_tokens
    )
    estimated_cost_usd = estimated_cost["usd"]
    estimated_cost_brl = estimated_cost["brl"]
    
    # --- Salvar outputs ---
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S")
    file_ts = now.strftime("%Y-%m-%d_%H%M%S")
    
    files_evaluated = list(all_results.keys())
    
    # JSON
    eval_output = {
        "eval_timestamp": timestamp,
        "gabarito_version": gab_version,
        "judge_model": OPENAI_MODEL,
        "judge_mode": mode,
        "files_evaluated": files_evaluated,
        "cost_summary": {
            "model": OPENAI_MODEL,
            "mode": cost_mode,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "api_calls": api_calls,
            "estimated_cost_usd": round(estimated_cost_usd, 4),
            "estimated_cost_brl": estimated_cost_brl,
            "usd_to_brl_rate": USD_TO_BRL,
        },
        "results": all_results,
    }
    eval_path = RESULTADOS_DIR / f"eval_{file_ts}.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(eval_output, f, ensure_ascii=False, indent=2)
    
    # Markdown
    just_path = RESULTADOS_DIR / f"justificativas_{file_ts}.md"
    with open(just_path, "w", encoding="utf-8") as f:
        f.write(f"# Justificativas — Avaliação {now.strftime('%Y-%m-%d')}\n\n")
        f.write(f"Juiz: {OPENAI_MODEL} | Modo: {mode} | Gabarito v{gab_version}\n")
        f.write(f"Arquivos: {len(files_evaluated)} | ")
        f.write(f"Chamadas API: {api_calls} | ")
        f.write(f"Tempo: {elapsed / 60:.1f} min\n")
        f.write("\n".join(all_justificativas))
        f.write("\n")
    
    # --- Print sumário final ---
    print(f"\n{'=' * 60}")
    print(f"  ✅ Avaliação concluída!")
    print(f"     Modo:           {mode}")
    print(f"     Modelo juiz:    {OPENAI_MODEL}")
    print(f"     Arquivos:       {len(files_evaluated)}")
    print(f"     Chamadas API:   {api_calls}")
    print(f"     Tokens:         {total_prompt_tokens//1000}K prompt + {total_completion_tokens//1000}K completion = {total_tokens//1000}K total")
    brl_display = f"{estimated_cost_brl:.2f}".replace(".", ",")
    print(f"     Custo estimado: ${estimated_cost_usd:.4f} (R$ {brl_display})")
    print(f"     Tempo total:    {elapsed / 60:.1f} min")
    print(f"     📄 {eval_path}")
    print(f"     📄 {just_path}")
    print(f"{'=' * 60}\n")
    
    # --- Limpeza (batch mode) ---
    if mode == MODE_BATCH and jsonl_path and l1_path:
        try:
            jsonl_path.unlink()
            l1_path.unlink()
            print(f"🧹 Arquivos temporários removidos")
        except Exception as e:
            print(f"⚠️  Erro ao remover arquivos temporários: {e}")


if __name__ == "__main__":
    main()