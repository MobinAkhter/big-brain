# brain/llm.py
import threading
from ctransformers import AutoModelForCausalLM
import requests, json

# ───────────────────────────────────────────
# Quantized GGUF model via ctransformers
# ───────────────────────────────────────────
# Place your Q4_0 GGUF llama3 model at models/llama3-8b-q4_0.gguf
_llm = AutoModelForCausalLM.from_pretrained(
    model="models/llama3-8b-q4_0.gguf",
    model_type="llama",
    library="ctransformers",
    device="mps",
    n_ctx=2048,
)
_llm.generate_kwargs = {"max_new_tokens": 256, "temperature":0.7}

# ───────────────────────────────────────────
# Embedding via Ollama’s API
# ───────────────────────────────────────────
OLLAMA = "http://localhost:11434"

def embed(text: str) -> list[float]:
    r = requests.post(
        f"{OLLAMA}/api/embed",
        json={"model": "mxbai-embed-large", "prompt": text}
    )
    data = r.json()
    return data["embedding"]

def chat(prompt: str) -> str:
    # run in blocking call; we’ll offload to a thread later
    return _llm.generate(prompt)
