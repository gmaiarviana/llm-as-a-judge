"""Lógica de avaliação: L1 local, L2-L4 via API."""

import json
from pathlib import Path

from .llm import call_openai, build_batch_line


# ============================================================
# CARREGAMENTO
# ============================================================

def load_gabarito(path: Path) -> tuple[dict, str]:
    """Carrega gabarito. Retorna (tasks_dict, version)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    version = data.get("version", "?")
    tasks = {k: v for k, v in data.items() if k.startswith("L")}
    return tasks, version


def load_system_prompt(path: Path) -> str:
    """Carrega system prompt do arquivo."""
    return path.read_text(encoding="utf-8")


def load_response_file(path: Path) -> dict:
    """Carrega um arquivo de respostas."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# L1 — STRING MATCH
# ============================================================

def evaluate_l1(response_letter: str, correct_letter: str) -> int:
    """Compara letra. Case-insensitive."""
    return 1 if response_letter.strip().upper() == correct_letter.strip().upper() else 0


# ============================================================
# L2-L4 — PROMPT BUILDER
# ============================================================

def build_user_prompt(task_id: str, gab_entry: dict, response_text: str) -> str:
    """Monta prompt de avaliação para uma task."""
    criteria_text = "\n".join(
        f"{i + 1}. {c}" for i, c in enumerate(gab_entry["criteria"])
    )
    return f"""Avalie a resposta abaixo contra os critérios listados.

TASK: {task_id}

PERGUNTA: {gab_entry["question"]}

CRITÉRIOS (TODOS devem ser atendidos para SUCESSO):
{criteria_text}

RESPOSTA AVALIADA:
\"\"\"
{response_text}
\"\"\"
"""


# ============================================================
# AVALIAÇÃO DE UM ARQUIVO — MODO SÍNCRONO
# ============================================================

def evaluate_file(
    file_path: Path,
    gabarito: dict,
    system_prompt: str,
    service_tier: str | None = None,
) -> tuple[str, dict, list, dict]:
    """
    Avalia todas as tasks de um arquivo de forma síncrona.
    Retorna (file_id, tasks_dict, justificativas_list, token_usage).
    
    Args:
        file_path: Caminho do arquivo de respostas
        gabarito: Dict com tasks do gabarito
        system_prompt: System prompt do juiz
        service_tier: "flex" para modo flex, None para standard
    
    Returns:
        Tupla (file_id, tasks, justificativas, token_usage)
        - token_usage: {"prompt_tokens": int, "completion_tokens": int, "api_calls": int}
    """
    data = load_response_file(file_path)
    file_id = data["metadata"]["id"]
    responses = data["responses"]

    tasks = {}
    justificativas = []
    token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "api_calls": 0,
    }

    sorted_tasks = sorted(responses.keys())
    total = len(sorted_tasks)

    for idx, task_id in enumerate(sorted_tasks, 1):
        response_text = responses[task_id]

        if task_id not in gabarito:
            print(f"  ⚠ {task_id} ausente no gabarito, pulando")
            continue

        gab = gabarito[task_id]
        level = gab["level"]

        # --- L1: local ---
        if level == 1:
            verdict = evaluate_l1(response_text, gab["answer"])
            tasks[task_id] = verdict
            r = response_text.strip().upper()
            c = gab["answer"].strip().upper()

            symbol = "✓" if verdict else "✗"
            if verdict:
                justificativas.append(f"✓ {task_id} — '{r}' = '{c}'")
            else:
                justificativas.append(f"✗ {task_id} — '{r}' ≠ '{c}'")
            print(f"  [{idx:>3}/{total}] {task_id}: {symbol} (L1)")
            continue

        # --- L2-L4: API ---
        user_prompt = build_user_prompt(task_id, gab, response_text)
        print(f"  [{idx:>3}/{total}] {task_id}: ", end="", flush=True)

        result, usage = call_openai(system_prompt, user_prompt, service_tier=service_tier)
        token_usage["api_calls"] += 1
        token_usage["prompt_tokens"] += usage["prompt_tokens"]
        token_usage["completion_tokens"] += usage["completion_tokens"]

        if result is None:
            print("❌ ERRO")
            tasks[task_id] = 0
            justificativas.append(
                f"\n### {file_id} — {task_id}\n"
                f"- ERRO: falha na chamada API\n"
                f"- **Veredicto: 0** (erro)\n"
            )
            continue

        verdict = result.get("verdict", 0)
        tasks[task_id] = verdict

        if verdict == 1:
            justificativas.append(f"✓ {task_id} — all criteria met")
            print("✓")
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
            print(f"✗ ({reason})")

    return file_id, tasks, justificativas, token_usage


# ============================================================
# PREPARAÇÃO DE BATCH
# ============================================================

def prepare_batch(
    response_files: list[Path],
    gabarito: dict,
    system_prompt: str,
    output_path: Path,
) -> tuple[int, int]:
    """
    Gera arquivo JSONL com todas as tasks L2-L4 de todos os arquivos.
    L1 é avaliado localmente (não vai pro batch).
    
    Args:
        response_files: Lista de arquivos de respostas
        gabarito: Dict com tasks do gabarito
        system_prompt: System prompt do juiz
        output_path: Caminho para salvar o JSONL
    
    Returns:
        Tupla (total_lines, total_l1)
        - total_lines: número de linhas no JSONL (tasks L2-L4)
        - total_l1: número de tasks L1 avaliadas localmente
    """
    batch_lines = []
    l1_results = {}
    total_l1 = 0
    
    for file_path in response_files:
        data = load_response_file(file_path)
        file_id = data["metadata"]["id"]
        responses = data["responses"]
        
        l1_results[file_id] = {}
        
        for task_id in sorted(responses.keys()):
            response_text = responses[task_id]
            
            if task_id not in gabarito:
                continue
            
            gab = gabarito[task_id]
            level = gab["level"]
            
            # L1: avaliar localmente
            if level == 1:
                verdict = evaluate_l1(response_text, gab["answer"])
                l1_results[file_id][task_id] = verdict
                total_l1 += 1
            
            # L2-L4: preparar para batch
            else:
                user_prompt = build_user_prompt(task_id, gab, response_text)
                custom_id = f"{file_id}____{task_id}"
                line = build_batch_line(custom_id, system_prompt, user_prompt)
                batch_lines.append(line)
    
    # Salvar JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(batch_lines))
    
    # Salvar resultados L1
    l1_path = output_path.with_suffix(".l1.json")
    with open(l1_path, "w", encoding="utf-8") as f:
        json.dump(l1_results, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Batch preparado: {len(batch_lines)} tasks L2-L4, {total_l1} tasks L1 locais")
    print(f"   JSONL: {output_path}")
    print(f"   L1: {l1_path}")
    
    return len(batch_lines), total_l1


# ============================================================
# PROCESSAMENTO DE RESULTADOS DO BATCH
# ============================================================

def process_batch_results(
    batch_results: list[dict],
    l1_results_path: Path,
    gabarito: dict,
) -> tuple[dict, list, dict]:
    """
    Processa resultados do batch + L1 locais e monta output final.
    
    Args:
        batch_results: Lista de resultados do batch (de download_batch_results())
        l1_results_path: Caminho do arquivo .l1.json
        gabarito: Dict com tasks do gabarito
    
    Returns:
        Tupla (all_results, all_justificativas, token_usage)
        - all_results: dict {file_id: {summary, tasks}}
        - all_justificativas: lista de strings com justificativas
        - token_usage: {"prompt_tokens": int, "completion_tokens": int, "api_calls": int}
    """
    # Carregar L1 locais
    with open(l1_results_path, encoding="utf-8") as f:
        l1_data = json.load(f)
    
    # Organizar por file_id
    by_file = {}
    for file_id, l1_tasks in l1_data.items():
        by_file[file_id] = {"tasks": dict(l1_tasks)}
    
    # Acumular tokens
    token_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "api_calls": 0,
    }
    
    # Processar resultados do batch
    for item in batch_results:
        custom_id = item["custom_id"]
        result = item["result"]
        usage = item["usage"]
        
        # Parsear custom_id: file_id____task_id
        parts = custom_id.split("____")
        if len(parts) != 2:
            print(f"⚠️  custom_id inválido: {custom_id}")
            continue
        
        file_id, task_id = parts
        
        # Inicializar file_id se necessário
        if file_id not in by_file:
            by_file[file_id] = {"tasks": {}}
        
        # Guardar resultado
        if result is None:
            by_file[file_id]["tasks"][task_id] = 0
        else:
            verdict = result.get("verdict", 0)
            by_file[file_id]["tasks"][task_id] = verdict
        
        # Acumular tokens
        token_usage["prompt_tokens"] += usage["prompt_tokens"]
        token_usage["completion_tokens"] += usage["completion_tokens"]
        token_usage["api_calls"] += 1
    
    # Gerar justificativas e sumários
    all_justificativas = []
    all_results = {}
    
    for file_id, file_data in sorted(by_file.items()):
        tasks = file_data["tasks"]
        file_justificativas = []
        
        # Gerar justificativas para cada task
        for task_id in sorted(tasks.keys()):
            verdict = tasks[task_id]
            
            if task_id not in gabarito:
                continue
            
            gab = gabarito[task_id]
            level = gab["level"]
            
            # L1: simples comparação
            if level == 1:
                if verdict:
                    file_justificativas.append(f"✓ {task_id} — match")
                else:
                    file_justificativas.append(f"✗ {task_id} — no match")
            
            # L2-L4: buscar resultado completo do batch
            else:
                # Encontrar resultado no batch
                batch_item = None
                for item in batch_results:
                    if item["custom_id"] == f"{file_id}____{task_id}":
                        batch_item = item
                        break
                
                if batch_item is None or batch_item["result"] is None:
                    file_justificativas.append(
                        f"\n### {file_id} — {task_id}\n"
                        f"- ERRO: resultado não encontrado ou inválido\n"
                        f"- **Veredicto: 0** (erro)\n"
                    )
                    continue
                
                result = batch_item["result"]
                verdict = result.get("verdict", 0)
                
                if verdict == 1:
                    file_justificativas.append(f"✓ {task_id} — all criteria met")
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
                    file_justificativas.append("\n".join(lines))
        
        # Computar sumário
        summary = compute_summary(tasks)
        
        # Guardar resultado final
        all_results[file_id] = {
            "summary": summary,
            "tasks": tasks,
        }
        
        # Adicionar justificativas
        all_justificativas.extend(file_justificativas)
    
    return all_results, all_justificativas, token_usage


# ============================================================
# SUMÁRIO
# ============================================================

def compute_summary(tasks: dict) -> dict:
    """Agrupa resultados por nível e calcula taxas."""
    levels = {}
    for task_id, verdict in tasks.items():
        level = task_id.split("_")[0]
        if level not in levels:
            levels[level] = {"evaluated": 0, "success": 0}
        levels[level]["evaluated"] += 1
        levels[level]["success"] += verdict

    summary = {}
    total_eval = 0
    total_success = 0

    for level in sorted(levels.keys()):
        e = levels[level]["evaluated"]
        s = levels[level]["success"]
        summary[level] = {
            "evaluated": e,
            "success": s,
            "rate": round(s / e, 2) if e > 0 else 0,
        }
        total_eval += e
        total_success += s

    summary["overall"] = {
        "evaluated": total_eval,
        "success": total_success,
        "rate": round(total_success / total_eval, 2) if total_eval > 0 else 0,
    }
    return summary