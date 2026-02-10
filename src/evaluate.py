"""Lógica de avaliação: L1 local, L2-L4 via API."""

import json
import time
from pathlib import Path

from llm import get_provider
from config import DELAY


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
# AVALIAÇÃO DE UM ARQUIVO
# ============================================================

def evaluate_file(
    file_path: Path, gabarito: dict, system_prompt: str
) -> tuple[str, dict, list, int]:
    """
    Avalia todas as tasks de um arquivo.
    Retorna (file_id, tasks_dict, justificativas_list, api_call_count).
    """
    data = load_response_file(file_path)
    file_id = data["metadata"]["id"]
    responses = data["responses"]

    tasks = {}
    justificativas = []
    api_calls = 0

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

        provider = get_provider()
        result = provider.call(system_prompt, user_prompt)
        api_calls += 1

        if result is None:
            print("❌ ERRO")
            tasks[task_id] = 0
            justificativas.append(
                f"\n### {file_id} — {task_id}\n"
                f"- ERRO: falha na chamada API\n"
                f"- **Veredicto: 0** (erro)\n"
            )
            time.sleep(DELAY)
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

        time.sleep(DELAY)

    return file_id, tasks, justificativas, api_calls


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