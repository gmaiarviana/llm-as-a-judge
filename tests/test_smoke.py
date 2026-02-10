import json
from pathlib import Path

from src.config import (
    BATCH_POLL_INTERVAL,
    GABARITO_PATH,
    OPENAI_MODEL,
    PROMPT_PATH,
    RESPOSTAS_DIR,
    calculate_cost,
)
from src.evaluate import build_user_prompt, load_gabarito, load_response_file, load_system_prompt
from src.llm import (
    build_batch_line,
    call_openai,
    create_batch,
    download_batch_results,
    poll_batch,
    upload_batch_file,
)


TASK_ID = "L3_02"
RESPONSE_FILE = "gemini25pro_run_01.json"


def load_inputs() -> tuple[str, dict, str]:
    system_prompt = load_system_prompt(PROMPT_PATH)
    gabarito, _ = load_gabarito(GABARITO_PATH)
    response_data = load_response_file(RESPOSTAS_DIR / RESPONSE_FILE)

    if TASK_ID not in gabarito:
        raise KeyError(f"Task {TASK_ID} nao encontrada no gabarito")
    if TASK_ID not in response_data.get("responses", {}):
        raise KeyError(f"Task {TASK_ID} nao encontrada em {RESPONSE_FILE}")

    response_text = response_data["responses"][TASK_ID]
    user_prompt = build_user_prompt(TASK_ID, gabarito[TASK_ID], response_text)
    return system_prompt, user_prompt, response_text


def test_sync_call() -> None:
    print("\nTeste 1: Chamada sincronica isolada")
    try:
        system_prompt, user_prompt, _response_text = load_inputs()
        result, usage = call_openai(system_prompt, user_prompt, service_tier="flex")

        print("response JSON (flex):")
        if result is None:
            print("null")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))

        verdict = None if result is None else result.get("verdict")
        cost = calculate_cost(
            OPENAI_MODEL,
            "flex",
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

        print(f"verdict (flex): {verdict}")
        print(f"usage (flex): {usage}")
        print(f"custo estimado (flex): ${cost['usd']:.6f}")

        flex_ok = result is not None
        if not flex_ok:
            print("❌ Flex retornou resposta nula")

        if not flex_ok:
            result_std, usage_std = call_openai(system_prompt, user_prompt, service_tier=None)
            print("response JSON (standard):")
            if result_std is None:
                print("null")
            else:
                print(json.dumps(result_std, indent=2, ensure_ascii=False))

            verdict_std = None if result_std is None else result_std.get("verdict")
            cost_std = calculate_cost(
                OPENAI_MODEL,
                "standard",
                usage_std.get("prompt_tokens", 0),
                usage_std.get("completion_tokens", 0),
            )

            print(f"verdict (standard): {verdict_std}")
            print(f"usage (standard): {usage_std}")
            print(f"custo estimado (standard): ${cost_std['usd']:.6f}")
            assert result_std is not None, "Resposta do juiz é None"

        assert result is not None, "Resposta do juiz é None"
        print("✅ Teste sincronico OK")
    except Exception as exc:
        print(f"❌ Teste sincronico erro: {exc}")


def test_batch_line() -> None:
    print("\nTeste 2: Geracao de linha batch")
    try:
        system_prompt, user_prompt, _response_text = load_inputs()
        line = build_batch_line("smoke::L3_02", system_prompt, user_prompt)
        payload = json.loads(line)

        print("JSON pretty:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        required_fields = ["custom_id", "method", "url", "body"]
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise ValueError(f"Campos obrigatorios ausentes: {missing}")

        print("✅ Teste batch line OK")
    except Exception as exc:
        print(f"❌ Teste batch line erro: {exc}")


def test_batch_flow() -> None:
    print("\nTeste 3: Fluxo batch minimal")
    try:
        system_prompt, user_prompt, _response_text = load_inputs()
        line = build_batch_line("smoke::L3_02", system_prompt, user_prompt)

        tmp_dir = Path(__file__).resolve().parents[1] / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = tmp_dir / "smoke_batch.jsonl"
        jsonl_path.write_text(line + "\n", encoding="utf-8")

        file_id = upload_batch_file(str(jsonl_path))
        batch_id = create_batch(file_id)
        batch = poll_batch(batch_id, interval=BATCH_POLL_INTERVAL)

        output_file_id = batch.output_file_id
        results = download_batch_results(output_file_id)

        if not results:
            raise RuntimeError("Nenhum resultado retornado pelo batch")

        first = results[0]
        verdict = None if first.get("result") is None else first["result"].get("verdict")
        usage = first.get("usage")

        print(f"verdict: {verdict}")
        print(f"usage: {usage}")
        print("✅ Teste batch completo OK")
    except Exception as exc:
        print(f"❌ Teste batch completo erro: {exc}")


def main() -> None:
    test_sync_call()
    test_batch_line()
    test_batch_flow()


if __name__ == "__main__":
    main()
