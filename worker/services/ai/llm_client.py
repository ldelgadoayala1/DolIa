import os
import json
from pathlib import Path

import requests

# -----------------------------------------------
# Config (gateway UNAB, mismo patron que RubricAgent)
# -----------------------------------------------

LLM_CONFIG_PATH = Path(os.getenv("LLM_CONFIG_PATH", "/config/llm_config.json"))

with open(LLM_CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

BASE_URL = CONFIG["base_url"].rstrip("/")
CHAT_URL = BASE_URL + CONFIG["endpoints"]["chat_completions"]
DEFAULT_MODEL = CONFIG.get("model", "gemma4:e2b")

API_KEY = os.getenv("LLM_API_KEY", "")


# -----------------------------------------------
# Cliente LLM
# -----------------------------------------------

def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0,
) -> str:
    """
    Llama al gateway (estilo OpenAI chat/completions) y retorna
    el content crudo del mensaje de respuesta.
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }

    response = requests.post(CHAT_URL, headers=headers, json=payload, timeout=300)

    if response.status_code != 200:
        raise RuntimeError(
            f"Error llamando al LLM. Status: {response.status_code}. Respuesta: {response.text}"
        )

    raw_response = response.json()
    return raw_response["choices"][0]["message"]["content"]


def call_llm_json(system_prompt: str, user_prompt: str, model: str | None = None) -> dict:
    """
    Llama al LLM esperando una respuesta JSON válida y la parsea.
    """
    content = chat_completion(system_prompt, user_prompt, model=model)

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Error parseando JSON del LLM: {e}. Contenido: {content}")
