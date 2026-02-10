import requests

OLLAMA_EMBEDDINGS_URL = "http://localhost:11434/api/embeddings"
EMBEDDING_MODEL = "all-minilm"
MAX_CHARS = 384  # Conservative limit to stay under 512 tokens


def get_embeddings(text: str) -> list:
    """Get embeddings from local Ollama all-minilm model."""
    # Truncate text to stay safe within model's 512 token limit
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
    
    payload = {
        "model": EMBEDDING_MODEL,
        "prompt": text,
    }
    
    response = requests.post(OLLAMA_EMBEDDINGS_URL, json=payload)
    response.raise_for_status()
    
    return response.json()["embedding"]
