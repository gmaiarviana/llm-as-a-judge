"""Interface para chamadas à API da OpenAI (síncronas e batch)."""

import json
import time
from datetime import datetime

from openai import OpenAI
from openai.types import Batch

from config import OPENAI_MODEL, BATCH_COMPLETION_WINDOW, BATCH_ENDPOINT

# Cliente OpenAI (usa OPENAI_API_KEY do ambiente automaticamente)
client = OpenAI()


def call_openai(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    service_tier: str | None = None,
) -> tuple[dict | None, dict]:
    """
    Faz chamada síncrona à API OpenAI com retry.
    
    Args:
        system_prompt: Instruções do sistema (juiz)
        user_prompt: Prompt do usuário (task a avaliar)
        model: Modelo a usar (default: config.OPENAI_MODEL)
        service_tier: "flex" para modo flex, None para standard
    
    Returns:
        Tupla (resultado_parseado, usage_info)
        - resultado_parseado: dict do JSON ou None se erro
        - usage_info: {"prompt_tokens": int, "completion_tokens": int}
    """
    model = model or OPENAI_MODEL
    timeout = 900 if service_tier == "flex" else 120  # 15min flex, 2min standard
    
    # Retry com backoff exponencial
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                timeout=timeout,
                **({"service_tier": service_tier} if service_tier else {}),
            )
            
            # Parsear resposta
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Extrair usage
            usage_info = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }
            
            return result, usage_info
            
        except (Exception) as e:
            error_type = type(e).__name__
            
            # Retry para erros recuperáveis
            if attempt < 2 and error_type in ["RateLimitError", "APITimeoutError", "InternalServerError", "ServiceUnavailableError"]:
                wait = 2 ** attempt  # 2s, 4s
                print(f"⚠️  {error_type}, retry {attempt+1}/3 em {wait}s...")
                time.sleep(wait)
                continue
            
            # Erro final
            print(f"❌ Erro na chamada OpenAI (tentativa {attempt+1}/3): {e}")
            return None, {"prompt_tokens": 0, "completion_tokens": 0}
    
    return None, {"prompt_tokens": 0, "completion_tokens": 0}


def build_batch_line(
    custom_id: str,
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
) -> str:
    """
    Gera linha JSONL para Batch API.
    
    Args:
        custom_id: ID único para rastrear a task
        system_prompt: Instruções do sistema
        user_prompt: Prompt do usuário
        model: Modelo a usar (default: config.OPENAI_MODEL)
    
    Returns:
        String JSON (uma linha do arquivo JSONL)
    """
    model = model or OPENAI_MODEL
    
    batch_request = {
        "custom_id": custom_id,
        "method": "POST",
        "url": BATCH_ENDPOINT,
        "body": {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
    }
    
    return json.dumps(batch_request, ensure_ascii=False)


def upload_batch_file(file_path: str) -> str:
    """
    Upload arquivo JSONL para OpenAI.
    
    Args:
        file_path: Caminho do arquivo .jsonl
    
    Returns:
        file_id da OpenAI
    """
    with open(file_path, "rb") as f:
        file_obj = client.files.create(file=f, purpose="batch")
    
    print(f"✅ Arquivo enviado: {file_obj.id}")
    return file_obj.id


def create_batch(input_file_id: str) -> str:
    """
    Cria um batch job.
    
    Args:
        input_file_id: ID do arquivo de input
    
    Returns:
        batch_id
    """
    batch = client.batches.create(
        input_file_id=input_file_id,
        endpoint=BATCH_ENDPOINT,
        completion_window=BATCH_COMPLETION_WINDOW,
    )
    
    print(f"✅ Batch criado: {batch.id}")
    return batch.id


def poll_batch(batch_id: str, interval: int = 30) -> Batch:
    """
    Poll batch até completar.
    
    Args:
        batch_id: ID do batch
        interval: Intervalo entre polls em segundos
    
    Returns:
        Batch object final
    
    Raises:
        RuntimeError: Se batch falhar, expirar ou for cancelado
    """
    start_time = time.time()
    
    while True:
        batch = client.batches.retrieve(batch_id)
        status = batch.status
        
        # Calcular tempo decorrido
        elapsed = (time.time() - start_time) / 60  # minutos
        
        # Status de progresso
        completed = batch.request_counts.completed or 0
        total = batch.request_counts.total or 0
        
        print(f"⏳ Batch {batch_id}: {status} ({completed}/{total} completed) — {elapsed:.1f} min elapsed")
        
        # Estados terminais
        if status == "completed":
            print(f"✅ Batch concluído!")
            return batch
        elif status in ["failed", "expired", "cancelled"]:
            raise RuntimeError(f"❌ Batch terminou com status: {status}")
        
        # Aguardar próximo poll
        time.sleep(interval)


def download_batch_results(output_file_id: str) -> list[dict]:
    """
    Download e parseia resultados do batch.
    
    Args:
        output_file_id: ID do arquivo de output
    
    Returns:
        Lista de dicts com custom_id, result (JSON parseado) e usage
    """
    # Download do arquivo
    content = client.files.content(output_file_id)
    lines = content.text.strip().split("\n")
    
    results = []
    
    for line in lines:
        try:
            response_obj = json.loads(line)
            custom_id = response_obj["custom_id"]
            
            # Extrair conteúdo e parsear JSON
            message_content = response_obj["response"]["body"]["choices"][0]["message"]["content"]
            result = json.loads(message_content)
            
            # Extrair usage
            usage = response_obj["response"]["body"]["usage"]
            
            results.append({
                "custom_id": custom_id,
                "result": result,
                "usage": {
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                },
            })
            
        except (json.JSONDecodeError, KeyError) as e:
            print(f"⚠️  Erro ao parsear linha do batch: {e}")
            results.append({
                "custom_id": response_obj.get("custom_id", "unknown"),
                "result": None,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            })
    
    print(f"✅ {len(results)} resultados parseados")
    return results
