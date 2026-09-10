"""TeachMe semantic embedding boundary."""

from ..config import search_index_config
from shared.semantic_embeddings import embed_text, knowledge_text


class EmbeddingClient:
    """Generate normalized embeddings using the shared configured model."""

    def __init__(self):
        self.dimension = search_index_config.INDEX_DIMENSION
        self.available = True

    def embed(self, item_type: str, data) -> list[float]:
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")
        return embed_text(knowledge_text(item_type, data))

    def embed_query(self, query: str) -> list[float]:
        return embed_text(query)
