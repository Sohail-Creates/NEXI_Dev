"""Text-only object retrieval through the existing TeachMe index and RAG policy."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "01_central_server", ROOT / "05_teachme_service"):
    sys.path.insert(0, str(directory))

from restricted_rag import RestrictedRAGPipeline, build_grounded_prompt
from shared.semantic_embeddings import embed_text, knowledge_text
from teachme_service.knowledge_base import PersistentKnowledgeBase
from teachme_service.sqlite_store import KnowledgeStore, initialize


@pytest.fixture
def knowledge(tmp_path, monkeypatch):
    from teachme_service.config import storage_config
    monkeypatch.setattr(storage_config, "BACKUP_DIR", str(tmp_path / "backups"))
    path = tmp_path / "knowledge.sqlite3"
    initialize(path)
    records = {}
    for key, kind, data in (
        ("bottle", "object", {"name": "My personal favorite water bottle", "category": "bottle",
                               "description": "I always drink water in it", "attributes": {}}),
        ("hometown", "fact", {"subject": "My hometown", "predicate": "is", "object": "Layyah Punjab Pakistan"}),
    ):
        records[key] = {"id": key, "type": kind, "data": data, "tags": [], "confidence": 1.0,
                        "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
                        "embedding": embed_text(knowledge_text(kind, data))}
    KnowledgeStore(path).save({}, records, {})
    return PersistentKnowledgeBase(str(path.with_suffix(".json")))


class IndexedTeachMe:
    def __init__(self, knowledge):
        self.knowledge = knowledge
        self.results = []
        self.queries = []

    async def search_by_embedding(self, query, k, threshold):
        self.queries.append(query)
        self.results = [{"id": item.id, "type": item.type.value,
                         "data": item.data.model_dump(mode="json"), "similarity": similarity}
                        for item, similarity in self.knowledge.search_by_embedding(
                            embed_text(query), k=k, threshold=threshold)]
        return {"results": self.results}


class GroundedLLM:
    async def generate_response(self, prompt, **kwargs):
        self.prompt = prompt
        text = prompt.split("FACTS:\n- ", 1)[1].split("\n", 1)[0]
        return True, {"response": text.removeprefix("[object] ")}


@pytest.mark.parametrize("query,expected", [
    ("My hometown", "hometown"),
    ("My personal favorite water bottle", "bottle"),
    ("What container do I always drink water from?", "bottle"),
    ("Do you know about my water bottle?", "bottle"),
    ("Tell me about my favorite bottle.", "bottle"),
    ("How do I repair a spacecraft engine?", None),
])
async def test_unified_text_retrieval(knowledge, monkeypatch, query, expected):
    monkeypatch.setattr(knowledge, "recognize_visual", lambda *_a, **_kw: pytest.fail("Visual recognition invoked"))
    client = IndexedTeachMe(knowledge)
    llm = GroundedLLM()
    result = await RestrictedRAGPipeline(client, llm).answer(query)
    assert set(knowledge._storage) == {"bottle", "hometown"}
    if expected is None:
        assert result.source == "no_match"
        assert not hasattr(llm, "prompt")
    else:
        assert result.source == "teachme_grounded"
        assert client.results[0]["id"] == expected
        assert client.results[0]["similarity"] == max(item["similarity"] for item in client.results)


async def test_deleted_object_excluded(knowledge):
    assert knowledge.forget_item("bottle")
    result = await RestrictedRAGPipeline(IndexedTeachMe(knowledge), GroundedLLM()).answer(
        "My personal favorite water bottle")
    assert result.source == "no_match"
    assert "bottle" not in knowledge._storage


def test_object_prompt_uses_only_textual_fields():
    item = {"type": "object", "data": {"name": "My bottle", "category": "bottle",
            "description": "For drinking water", "attributes": {"private": "secret-attribute",
            "instance_embedding": [12345.6789]}}, "visual_embedding": [98765.4321]}
    prompt, texts = build_grounded_prompt("What is my bottle?", [item])
    assert "[object]" in prompt
    assert texts == ["My bottle For drinking water"]
    assert all(value not in prompt for value in ("secret-attribute", "12345", "98765", "embedding"))


def test_legacy_object_backfilled_once_and_existing_embeddings_reused(knowledge, monkeypatch):
    record = knowledge._storage["bottle"]
    original = record.embedding
    record.embedding = None
    knowledge.save_to_file()
    calls = []
    monkeypatch.setattr(knowledge.embedding_client, "embed", lambda kind, data: calls.append(kind) or original)
    knowledge.load_from_file()
    knowledge.load_from_file()
    assert calls == ["object"]
    assert knowledge._storage["bottle"].embedding == original
    assert KnowledgeStore(knowledge._store.database).read()["storage"]["bottle"]["embedding"] == original


@pytest.mark.parametrize("vector", [None, [], [1.0] * 64, [0.0] * 384, [float("nan")] * 384])
def test_invalid_object_semantic_vector_refreshed(knowledge, monkeypatch, vector):
    item = knowledge._storage["bottle"]
    expected = item.embedding
    item.embedding = vector
    calls = []
    monkeypatch.setattr(knowledge.embedding_client, "embed", lambda *args: calls.append(args[0]) or expected)
    assert knowledge._refresh_object_semantic_embedding(item)
    assert not knowledge._refresh_object_semantic_embedding(item)
    assert calls == ["object"]


def test_stale_version_refreshed_once_without_changing_fact_or_visual(knowledge, monkeypatch):
    import copy
    item = knowledge._storage["bottle"]
    item.visual_embedding = [1.0] * 64
    item.instance_prototypes = [[1.0] * 512]
    item.instance_embedding_model = "torchvision-resnet18-imagenet1k-v1"
    item.instance_embedding_version = 1
    item.semantic_embedding_version = "old-version"
    before = copy.deepcopy(item.model_dump(mode="json"))
    fact = knowledge._storage["hometown"].model_dump(mode="json")
    knowledge.save_to_file()
    expected = embed_text(knowledge_text("object", item.data.model_dump()))
    calls = []
    monkeypatch.setattr(knowledge.embedding_client, "embed", lambda *args: calls.append(args[0]) or expected)
    knowledge.load_from_file()
    knowledge.load_from_file()
    assert calls == ["object"]
    after = knowledge._storage["bottle"].model_dump(mode="json")
    for field in before:
        if field not in {"embedding", "semantic_embedding_hash", "semantic_embedding_version"}:
            assert after[field] == before[field]
    assert knowledge._storage["hometown"].model_dump(mode="json") == fact


def test_canonical_text_update_invalidates_and_reindexes_once(knowledge, monkeypatch):
    from teachme_service.models import ObjectData
    from shared.semantic_embeddings import object_semantic_hash
    calls = []
    original_embed = knowledge.embedding_client.embed
    monkeypatch.setattr(knowledge.embedding_client, "embed", lambda *args: calls.append(args[0]) or original_embed(*args))
    item = knowledge.update_item("bottle", data=ObjectData(name="My travel mug", description="For coffee"))
    assert item.semantic_embedding_hash == object_semantic_hash(item.data.model_dump())
    assert knowledge.search_by_embedding(embed_text("My travel mug"), threshold=0.45)[0][0].id == "bottle"
    knowledge.load_from_file()
    assert calls == ["object"]


def test_legacy_detector_metadata_not_conversational_text():
    from shared.semantic_embeddings import object_semantic_text
    assert object_semantic_text({"name": "This is my personal favorite water bottle", "category": "wine glass",
        "description": "Vision-detected wine glass (confidence: 0.72) with rectangular shape"}) == "This is my personal favorite water bottle"


def test_label_only_object_prompt_is_answerable_without_changing_fact_prompt():
    item = {"type": "object", "data": {"name": "My bottle"}}
    prompt, texts = build_grounded_prompt("Tell me about my bottle", [item])
    assert "label is itself taught knowledge" in prompt
    assert "do not invent uses or locations" in prompt
    assert texts == ["My bottle"]
    fact = {"type": "fact", "data": {"subject": "My hometown", "predicate": "is", "object": "Layyah"}}
    prompt, _ = build_grounded_prompt("My hometown", [fact])
    assert "label is itself taught knowledge" not in prompt
    assert "FACTS:\n- My hometown is Layyah\nQUESTION:\nMy hometown" in prompt


def test_new_object_reuses_already_generated_canonical_vector(knowledge, monkeypatch):
    from teachme_service.models import ObjectData
    data = ObjectData(name="My travel mug")
    embedding = knowledge.embedding_client.embed("object", data)
    monkeypatch.setattr(knowledge.embedding_client, "embed", lambda *args: pytest.fail("Canonical vector regenerated"))
    key = knowledge.learn_object(data, embedding=embedding)
    knowledge.load_from_file()
    assert knowledge._storage[key].embedding == embedding


class CombinedGroundedLLM:
    def __init__(self):
        self.calls = 0

    async def generate_response(self, prompt, **kwargs):
        self.calls += 1
        self.prompt = prompt
        lines = prompt.split("FACTS:\n", 1)[1].split("\nQUESTION:", 1)[0].splitlines()
        return True, {"response": ". ".join(line.removeprefix("- ").removeprefix("[object] ") for line in lines)}


async def test_compound_fact_object_uses_same_bounded_search_and_one_llm(knowledge):
    client, llm = IndexedTeachMe(knowledge), CombinedGroundedLLM()
    result = await RestrictedRAGPipeline(client, llm).answer("Tell me about my hometown and my water bottle.")
    assert result.source == "teachme_grounded"
    assert "Layyah" in result.response and "water bottle" in result.response
    assert client.queries == ["my hometown", "my water bottle"]
    assert llm.calls == 1
    assert "visual_embedding" not in llm.prompt and "instance" not in llm.prompt


async def test_compound_two_facts_excludes_irrelevant_and_deleted(knowledge):
    from teachme_service.models import FactData
    data = FactData(subject="My favorite color", predicate="is", object="blue")
    key = knowledge.learn_fact(data, embedding=knowledge.embedding_client.embed("fact", data))
    client, llm = IndexedTeachMe(knowledge), CombinedGroundedLLM()
    result = await RestrictedRAGPipeline(client, llm).answer("Tell me about my hometown and my favorite color.")
    assert result.source == "teachme_grounded"
    assert "Layyah" in result.response and "blue" in result.response
    assert "bottle" not in llm.prompt
    assert knowledge.forget_item(key)
    result = await RestrictedRAGPipeline(client, llm).answer("Tell me about my hometown and my favorite color.")
    assert result.source == "teachme_grounded"
    assert "Layyah" in result.response and "blue" not in llm.prompt


async def test_known_unknown_compound_only_supplies_known_context(knowledge):
    client, llm = IndexedTeachMe(knowledge), CombinedGroundedLLM()
    result = await RestrictedRAGPipeline(client, llm).answer("Tell me about my hometown and my spacecraft engine.")
    assert result.source == "teachme_grounded"
    facts = llm.prompt.split("FACTS:\n", 1)[1].split("\nQUESTION:", 1)[0]
    assert "Layyah" in facts and "bottle" not in facts and "engine" not in facts


def test_compound_clause_count_bounded_and_ordinary_and_preserved():
    from restricted_rag import _retrieval_clauses, RAG_TOP_K
    assert len(_retrieval_clauses("my A and my B and my C and my D")) <= RAG_TOP_K
    assert _retrieval_clauses("Tell me about Trinidad and Tobago") == ["Tell me about Trinidad and Tobago"]
