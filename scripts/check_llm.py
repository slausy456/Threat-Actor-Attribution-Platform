"""Check configured LLM connectivity without displaying credentials or response data."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
sys.path.insert(0, str(ROOT / "backend"))

from app.services.llm_explain.explainer import PROVIDERS


def main() -> None:
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    default_model = PROVIDERS.get(provider, (None, "unknown"))[1]
    model = os.getenv("LLM_MODEL", default_model).strip() or default_model

    if provider not in PROVIDERS:
        print(f"Provider: {provider}\nModel: {model}\nHTTP status: not sent\nLatency: 0 ms")
        print("Next step: set LLM_PROVIDER to a supported provider (groq or openai).")
        return
    if not api_key:
        print(f"Provider: {provider}\nModel: {model}\nHTTP status: not sent\nLatency: 0 ms")
        print("Next step: set LLM_API_KEY in your environment or .env file.")
        return

    endpoint, _ = PROVIDERS[provider]
    started_at = time.perf_counter()
    try:
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 8,
                "temperature": 0.0,
            },
            timeout=10.0,
        )
    except httpx.TimeoutException:
        latency = round((time.perf_counter() - started_at) * 1000)
        print(f"Provider: {provider}\nModel: {model}\nHTTP status: timeout\nLatency: {latency} ms")
        print("Next step: check connectivity and retry; the request exceeded 10 seconds.")
        return
    except httpx.RequestError:
        latency = round((time.perf_counter() - started_at) * 1000)
        print(f"Provider: {provider}\nModel: {model}\nHTTP status: unavailable\nLatency: {latency} ms")
        print("Next step: check network access and the provider endpoint.")
        return

    status = response.status_code
    latency = round((time.perf_counter() - started_at) * 1000)
    print(f"Provider: {provider}\nModel: {model}\nHTTP status: {status}\nLatency: {latency} ms")
    if status == 401:
        print("Next step: verify that LLM_API_KEY is valid and enabled for this provider.")
    elif status in {400, 404}:
        print(f"Next step: verify that LLM_MODEL is available to this provider: {model}.")
    elif status == 429:
        print("Next step: check provider quota and rate limits, then retry later.")
    elif 200 <= status < 300:
        print("Connectivity check succeeded.")
    else:
        print("Next step: check the provider's status and request requirements.")


if __name__ == "__main__":
    main()
