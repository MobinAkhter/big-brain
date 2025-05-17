import requests

OLLAMA = "http://localhost:11434"

def _post_json(path, payload):
    r = requests.post(f"{OLLAMA}{path}", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def embed(text: str) -> list[float]:
    data = _post_json(
        "/api/embeddings",
        {"model": "mxbai-embed-large", "prompt": text}
    )
    # Ollama returns either {"embedding":[...]} or {"data":[...]}
    return data.get("embedding") or data.get("data") or []

def chat(prompt: str) -> str:
    data = _post_json(
        "/api/chat",
        {"model": "llama3:8b",
         "messages": [{"role": "user", "content": prompt}],
         "stream": False}
    )
    return data.get("message", {}).get("content", "")
