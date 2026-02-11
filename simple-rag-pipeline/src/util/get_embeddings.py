from sentence_transformers import SentenceTransformer

# Using sentence-transformers for local embeddings
# all-MiniLM-L6-v2: 384-dimensional embeddings, lightweight and fast
model = SentenceTransformer('all-MiniLM-L6-v2')


def get_embeddings(text: str) -> list:
    """Get embeddings using sentence-transformers."""
    # Generate embeddings using the model
    embedding = model.encode(text, convert_to_tensor=False)
    return embedding.tolist()
