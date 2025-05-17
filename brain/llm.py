import requests

OLLAMA = "http://localhost:11434"

def _post_json(path, payload):
    try:
        r = requests.post(f"{OLLAMA}{path}", json=payload, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print("Error: Could not find the embedding model on Ollama. Ensure Ollama is running and the 'nomic-embed-text' model is installed (run 'ollama pull nomic-embed-text').")
        raise

def embed(text: str) -> list[float]:
    data = _post_json(
        "/api/embeddings",
        {"model": "nomic-embed-text", "prompt": text}
    )
    return data.get("embedding") or data.get("data") or []

def chat(prompt: str) -> str:
    data = _post_json(
        "/api/chat",
        {"model": "llama3:8b",
         "messages": [{"role": "user", "content": prompt}],
         "stream": False}
    )
    return data.get("message", {}).get("content", "")