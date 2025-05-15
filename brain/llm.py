import requests, json

OLLAMA = "http://localhost:11434"

def embed(text: str) -> list[float]:
    r = requests.post(f"{OLLAMA}/api/embeddings",  # Correct endpoint
                      json={"model": "mxbai-embed-large", "prompt": text})
    if r.status_code != 200:
        raise Exception(f"API request failed with status {r.status_code}: {r.text}")
    data = r.json()
    if "embedding" not in data:
        raise Exception(f"API response missing 'embedding' key: {data}")
    return data["embedding"]

def chat(prompt: str) -> str:
    r = requests.post(f"{OLLAMA}/api/chat",
                      json={"model": "llama3:8b",
                            "messages": [{"role": "user", "content": prompt}],
                            "stream": False})
    if r.status_code != 200:
        raise Exception(f"API request failed with status {r.status_code}: {r.text}")
    data = r.json()
    if "message" not in data or "content" not in data["message"]:
        raise Exception(f"API response missing expected keys: {data}")
    return data["message"]["content"]