"""
Single call() interface for Ollama (local, Q4), OpenAI, and Groq (fp16).
run.py never branches on model type — this module handles it transparently.

Track assignment:
  Q4 track  (local)  → Ollama       → model names like "mistral:7b", "qwen2.5:32b"
  fp16 track (cloud) → Groq API     → model names prefixed "groq/"
  Ceiling            → OpenAI API   → model names like "gpt-4o"
"""
import os
import re
import time
import httpx


OLLAMA_BASE_URL = "http://localhost:11434"
OPENAI_BASE_URL = "https://api.openai.com/v1"
GROQ_BASE_URL   = "https://api.groq.com/openai/v1"

OPENAI_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo"}

# Groq model IDs — prefix "groq/" in config to route here
# Underlying ID (after stripping prefix) is sent to Groq API
GROQ_MODELS = {
    "groq/llama-3.1-8b-instant",
    "groq/llama-3.3-70b-versatile",
    "groq/qwen/qwen3-32b",
}


def call(model: str, system_prompt: str, user_message: str, timeout: int = 60) -> str:
    """
    Call a model and return the raw response string.
    Raises RuntimeError on network/API failure — caller handles retry logic.
    """
    if model in OPENAI_MODELS:
        return _call_openai(model, system_prompt, user_message, timeout)
    if model in GROQ_MODELS:
        groq_model_id = model[len("groq/"):]   # strip leading "groq/" only
        return _call_groq(groq_model_id, system_prompt, user_message, timeout)
    return _call_ollama(model, system_prompt, user_message, timeout)


def _chat_payload(model: str, system_prompt: str, user_message: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0,
    }


def _call_openai(model: str, system_prompt: str, user_message: str, timeout: int) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable not set")

    max_retries = 5
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    f"{OPENAI_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=_chat_payload(model, system_prompt, user_message),
                )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise RuntimeError(f"OpenAI request failed: {e}") from e

        if resp.status_code == 429:
            body = resp.text
            match_s  = re.search(r"try again in (\d+(?:\.\d+)?)s", body)
            match_ms = re.search(r"try again in (\d+(?:\.\d+)?)ms", body)
            if match_s:
                wait = float(match_s.group(1)) + 1.0
            elif match_ms:
                wait = float(match_ms.group(1)) / 1000.0 + 1.0
            else:
                wait = 5.0
            print(f"\n  [rate limit] waiting {wait:.0f}s before retry...", flush=True)
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text}")

        return resp.json()["choices"][0]["message"]["content"]

    raise RuntimeError(f"OpenAI rate limit exceeded after {max_retries} retries")


def _call_groq(model: str, system_prompt: str, user_message: str, timeout: int) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set")

    max_retries = 5
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=_chat_payload(model, system_prompt, user_message),
                )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
            raise RuntimeError(f"Groq request failed: {e}") from e

        if resp.status_code == 429:
            # Parse "Please try again in X.XXs" from error message
            body = resp.text
            match = re.search(r"try again in (\d+(?:\.\d+)?)s", body)
            wait = float(match.group(1)) + 1.0 if match else 20.0
            print(f"\n  [rate limit] waiting {wait:.0f}s before retry...", flush=True)
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text}")

        return resp.json()["choices"][0]["message"]["content"]

    raise RuntimeError(f"Groq rate limit exceeded after {max_retries} retries")


def _call_ollama(model: str, system_prompt: str, user_message: str, timeout: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {"temperature": 0},
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        raise RuntimeError(f"Ollama request failed: {e}") from e

    if resp.status_code != 200:
        raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text}")

    return resp.json()["message"]["content"]
