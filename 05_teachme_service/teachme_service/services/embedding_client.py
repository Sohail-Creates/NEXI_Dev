"""Embedding client boundary retained for Phase 4 integration."""

from ..config import search_index_config


class EmbeddingClient:
    """Expose configuration without replacing the current embedding generator.

    The knowledge base only constructs this client. Semantic embedding generation
    and its caller contract remain unimplemented until Phase 4 (NEXI-018).
    """

    def __init__(self):
        self.dimension = search_index_config.INDEX_DIMENSION
        self.available = False
