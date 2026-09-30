"""Standing producer/consumer contracts for every Phase 1-7 service pair."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import sys
from types import MethodType, SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
CENTRAL = ROOT / "01_central_server"
ENROLLMENT = ROOT / "06_enrollment_service"
AUDIO = ROOT / "03_audio_service"
TEACHME = ROOT / "05_teachme_service"
VISION = ROOT / "02_vision_service"
sys.path[:0] = [str(ROOT), str(CENTRAL), str(ENROLLMENT), str(AUDIO), str(TEACHME), str(VISION)]

os.environ.setdefault("AUTH_ENFORCEMENT_ENABLED", "true")
os.environ.setdefault("NEXI_INTERNAL_SERVICE_TOKEN", "phase8-contract-service-token")
os.environ.setdefault("NEXI_JWT_SECRET", "phase8-contract-jwt-secret-at-least-32-bytes")

from app.clients import audio_client as enrollment_audio_module
from app.clients import central_server_client as enrollment_central_module
from app.clients import vision_client as enrollment_vision_module
from audio_service.services.conversation_orchestrator import ConversationOrchestrator
from shared.clients.llm_client import LLMServiceClient
from shared.clients.models import ServiceCallResult
from shared.semantic_embeddings import SEMANTIC_EMBEDDING_DIMENSION
from teachme_connector import TeachMeConnector
from teachme_service.config import search_index_config
from teachme_service.models import KnowledgeItem, LearningType, ObjectData
from teachme_service.object_processor import ObjectProcessor
from teachme_service.sqlite_store import KnowledgeStore, initialize


pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_taught_object_keeps_visual_and_semantic_vectors_separate(tmp_path) -> None:
    class VisionStub:
        async def get_vision_attributes(self, name):
            assert name == "bottle"
            return {"detections": [
                {"class_name": "bottle", "confidence": 0.9,
                 "bounding_box": {"x": 1, "y": 2, "width": 20, "height": 30},
                 "embedding": [0.125] * 64},
                {"class_name": "person", "confidence": 0.8,
                 "bounding_box": {"x": 2, "y": 3, "width": 40, "height": 50},
                 "embedding": [0.25] * 64},
            ]}

    processor = ObjectProcessor()
    processor.vision_connector = VisionStub()
    processed = await processor.process_object_async(ObjectData(name="bottle"))
    assert processed.visual_embedding == [0.125] * 64
    assert "visual_embedding" not in processed.attributes
    assert processed.attributes["detected_class"] == "bottle"
    now = datetime.utcnow()
    item = KnowledgeItem(id="test", type=LearningType.OBJECT, data=processed,
                         tags=[], confidence=1.0, created_at=now, updated_at=now,
                         embedding=[0.5] * 384, visual_embedding=processed.visual_embedding)
    reloaded = KnowledgeItem.model_validate(item.model_dump(mode="json"))
    assert len(reloaded.embedding) == 384 and len(reloaded.visual_embedding) == 64
    assert "visual_embedding" not in reloaded.data.model_dump()
    database = tmp_path / "knowledge.sqlite3"
    initialize(database)
    store = KnowledgeStore(database)
    store.save({}, {item.id: item.model_dump(mode="json")}, {})
    persisted = KnowledgeItem.model_validate(store.read()["storage"][item.id])
    assert len(persisted.embedding) == 384 and persisted.visual_embedding == [0.125] * 64
    old = KnowledgeItem.model_validate({key: value for key, value in item.model_dump(mode="json").items()
                                        if key != "visual_embedding"})
    assert old.visual_embedding is None and len(old.embedding) == 384
    assert "visual_embedding" not in old.model_dump(mode="json")


@pytest.mark.asyncio
async def test_selected_vision_observation_skips_second_capture() -> None:
    from pydantic import ValidationError

    class NoSecondCapture:
        async def get_vision_attributes(self, name):
            raise AssertionError("Vision must not capture again for a selected observation")

    observation = {
        "class_id": 40, "class_name": "wine glass", "confidence": 0.85,
        "bounding_box": {"x": 10, "y": 20, "width": 30, "height": 40},
        "embedding": [0.125] * 64, "embedding_model": "yolov8n-p3-roi-avg-v1",
        "embedding_dimension": 64,
    }
    processor = ObjectProcessor()
    processor.vision_connector = NoSecondCapture()
    processed = await processor.process_object_async(
        ObjectData(name="My glass", attributes={"bounding_box": {"x": 999}, "detected_class": "wrong"},
                   vision_observation=observation)
    )
    assert processed.visual_embedding == observation["embedding"]
    assert processed.attributes["detected_class"] == "wine glass"
    assert processed.attributes["bounding_box"] == observation["bounding_box"]
    assert processed.attributes["detected_class"] == observation["class_name"]
    assert "vision_observation" not in processed.model_dump()

    with pytest.raises(ValidationError):
        ObjectData(name="bad", vision_observation={**observation, "embedding": [0.1] * 63})
    with pytest.raises(ValidationError):
        ObjectData(name="bad", vision_observation={**observation, "embedding": [float("nan")] * 64})
    with pytest.raises(ValidationError):
        ObjectData(name="bad", vision_observation={**observation, "embedding": [0.0] * 64})


def test_object_upload_distinguishes_bad_image_from_model_failure(monkeypatch) -> None:
    import io
    import cv2
    import numpy as np
    from fastapi import HTTPException, UploadFile
    from vision_service.routes import detection

    monkeypatch.setattr(detection, "_resource_pool", SimpleNamespace(
        get_object_detector=lambda: SimpleNamespace(detect=lambda image: None)
    ))
    with pytest.raises(HTTPException) as bad_image:
        detection.detect_objects_from_upload(UploadFile(file=io.BytesIO(b"bad"), filename="bad.png"))
    assert bad_image.value.status_code == 400
    assert bad_image.value.detail["code"] == "INVALID_IMAGE"

    encoded, image = cv2.imencode(".png", np.zeros((32, 32, 3), dtype=np.uint8))
    assert encoded
    with pytest.raises(HTTPException) as model_error:
        detection.detect_objects_from_upload(UploadFile(file=io.BytesIO(image.tobytes()), filename="valid.png"))
    assert model_error.value.status_code == 503
    assert model_error.value.detail["code"] == "OBJECT_INFERENCE_FAILED"


def _fault(name: str) -> bool:
    return os.getenv("PHASE8_FAULT") == name


def _spec(service: str) -> dict:
    return json.loads((ROOT / "docs" / "openapi" / f"{service}.json").read_text(encoding="utf-8"))


class _Response:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> dict:
        return self._body


class _HTTPXClient:
    response = _Response(200, {})
    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        self.headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url: str, **kwargs):
        type(self).calls.append({"method": "POST", "url": url, **kwargs})
        return type(self).response


@pytest.mark.asyncio
async def test_contract_central_teachme_payload_and_embedding_dimension() -> None:
    connector = TeachMeConnector(base_url="http://teachme.test", config={"max_retries": 1})
    if _fault("contract_central_teachme"):
        connector.embedding_dimension = 128
    calls: list[dict] = []

    async def record_request(self, method, endpoint, data=None, timeout=None, user_id=None):
        calls.append({"method": method, "endpoint": endpoint, "data": data, "user_id": user_id})
        return {"results": []} if "search" in endpoint else {"success": True, "item_id": "fact-1"}

    connector.request = MethodType(record_request, connector)
    learned = await connector.learn_item(
        "fact", {"subject": "NEXI", "predicate": "dock location", "object": "blue sofa"}
    )
    await connector.search_by_embedding("Where is NEXI's dock?", k=3, threshold=0.55, user_id="user-a")

    teachme_spec = _spec("teachme")
    learning_schema = teachme_spec["components"]["schemas"]["LearningRequest"]
    search_operation = teachme_spec["paths"]["/knowledge/search/embedding"]["post"]
    query_names = {parameter["name"] for parameter in search_operation["parameters"]}
    parsed = urlparse(calls[1]["endpoint"])
    assert connector.embedding_dimension == search_index_config.INDEX_DIMENSION == SEMANTIC_EMBEDDING_DIMENSION
    assert set(calls[0]["data"]) == set(learning_schema["properties"])
    assert parsed.path == "/knowledge/search/embedding"
    assert set(parse_qs(parsed.query)) == query_names
    assert calls[1]["user_id"] == "user-a" and learned["success"]
    print(
        f"CONTRACT Central-TeachMe PASS dimension={connector.embedding_dimension} "
        f"learn_fields={sorted(calls[0]['data'])} search_params={sorted(query_names)}"
    )


@pytest.mark.asyncio
async def test_contract_enrollment_vision_upload_and_response(monkeypatch, tmp_path) -> None:
    image = tmp_path / "face.jpg"
    image.write_bytes(b"fixture-jpeg")
    body = {
        "status": "success",
        "timestamp": "2026-09-11T00:00:00Z",
        "frame_width": 32,
        "frame_height": 32,
        "faces_detected": 1,
        "faces": [{
            "face_id": 0,
            "bounding_box": {"x": 0, "y": 0, "width": 32, "height": 32},
            "confidence": 0.98,
            "embedding": [0.1, 0.2],
            "embedding_model": "Facenet",
        }],
    }
    if _fault("contract_enrollment_vision"):
        body = {"face_detected": True, "embedding": [0.1, 0.2], "confidence": 0.98}
    _HTTPXClient.calls = []
    _HTTPXClient.response = _Response(200, body)
    monkeypatch.setattr(enrollment_vision_module.httpx, "AsyncClient", _HTTPXClient)
    client = enrollment_vision_module.VisionClient()
    client.max_retries = 1
    result = await client.get_face_embedding(str(image))
    call = _HTTPXClient.calls[0]
    path = urlparse(call["url"]).path
    assert path in _spec("vision")["paths"]
    assert path == "/api/v1/detect/faces/upload"
    assert result == {"embedding": [0.1, 0.2], "confidence": 0.98, "face_detected": True}
    print(f"CONTRACT Enrollment-Vision PASS path={path} multipart=file response=faces[0].embedding")


@pytest.mark.asyncio
async def test_contract_enrollment_audio_process_voice_shape(monkeypatch) -> None:
    wrapper = enrollment_audio_module.AudioClient()
    seen: dict = {}

    async def process_voice(**kwargs):
        seen.update(kwargs)
        data = {"embedding": [0.3, 0.4], "quality_score": 0.91}
        if _fault("contract_enrollment_audio"):
            data = {"voice_vector": [0.3, 0.4], "quality_score": 0.91}
        return ServiceCallResult(success=True, data=data)

    monkeypatch.setattr(wrapper.client, "process_voice", process_voice)
    result = await wrapper.enroll_speaker("user-a", b"RIFF-synthesized-wave")
    operation = _spec("audio")["paths"]["/api/v1/process-voice"]["post"]
    assert "multipart/form-data" in operation["requestBody"]["content"]
    assert seen == {"audio_file_bytes": b"RIFF-synthesized-wave", "filename": "enrollment_user-a.wav"}
    assert result["embeddings"] == [0.3, 0.4] and result["speaker_id"] == "user-a"
    print("CONTRACT Enrollment-Audio PASS path=/api/v1/process-voice field=embedding wrapper=embeddings")


@pytest.mark.asyncio
async def test_contract_enrollment_central_registration(monkeypatch) -> None:
    _HTTPXClient.calls = []
    body = {"user_id": "user-a", "status": "registered", "message": "ok"}
    if _fault("contract_enrollment_central"):
        body = {"id": "user-a", "status": "registered", "message": "ok"}
    _HTTPXClient.response = _Response(200, body)
    monkeypatch.setattr(enrollment_central_module.httpx, "AsyncClient", _HTTPXClient)
    client = enrollment_central_module.CentralServerClient()
    client.max_retries = 1
    payload = {"name": "Ada", "face_embeddings": [[0.1]], "voice_embeddings": [[0.2]]}
    result = await client.register_user(payload)
    call = _HTTPXClient.calls[0]
    path = urlparse(call["url"]).path
    assert path == "/users" and path in _spec("central")["paths"]
    assert set(call["json"]) >= {"name", "face_embeddings", "voice_embeddings"}
    assert result["user_id"] == "user-a"
    print("CONTRACT Enrollment-Central PASS path=/users request=name+embeddings response=user_id")


@pytest.mark.asyncio
async def test_contract_audio_central_restricted_rag_boundary() -> None:
    orchestrator = object.__new__(ConversationOrchestrator)
    orchestrator.central_url = "http://central.test"
    orchestrator.focus_mode_client = SimpleNamespace(async_defer_if_needed=lambda context: _completed(None))
    seen: dict = {}

    async def post(self, url, **kwargs):
        seen.update({"url": url, **kwargs})
        if _fault("contract_audio_central"):
            return {"success": True, "text": "Beside the sofa."}
        return {"success": True, "response": "Beside the sofa.", "source": "teachme_grounded"}

    orchestrator._post_with_retry = MethodType(post, orchestrator)
    answer = await orchestrator.generate_llm_response("Where is the dock?", "user-a")
    path = urlparse(seen["url"]).path
    assert path == "/api/v1/rag/query" and path in _spec("central")["paths"]
    assert seen["json_data"] == {"query": "Where is the dock?"}
    assert seen["headers"]["X-NEXI-Trusted-User-ID"] == "user-a"
    assert answer == "Beside the sofa."
    print("CONTRACT Audio-Central PASS path=/api/v1/rag/query request=query response=response user_header=user-a")


async def _completed(value):
    return value


@pytest.mark.asyncio
async def test_contract_central_llm_generation_shape(monkeypatch) -> None:
    body = {"success": True, "text": "Beside the sofa.", "metadata": {"model": "fixture"}}
    if _fault("contract_central_llm"):
        body = {"success": True, "response": "Beside the sofa.", "metadata": {"model": "fixture"}}
    _HTTPXClient.calls = []
    _HTTPXClient.response = _Response(200, body)
    import shared.clients.llm_client as llm_module

    monkeypatch.setattr(llm_module.httpx, "AsyncClient", _HTTPXClient)
    client = LLMServiceClient(base_url="http://llm.test", focus_mode_client=SimpleNamespace(
        async_defer_if_needed=lambda context: _completed(None)
    ))
    success, result = await client.generate_response(
        "SERVER-BUILT GROUNDED PROMPT", language="en", max_response_tokens=128, temperature=0.2,
        request_context="teachme",
    )
    call = _HTTPXClient.calls[0]
    path = urlparse(call["url"]).path
    generation_schema = _spec("llm")["components"]["schemas"]["GenerationRequest"]
    assert path == "/api/v1/generate" and path in _spec("llm")["paths"]
    assert set(call["json"]) <= set(generation_schema["properties"])
    assert "system_prompt" not in call["json"]
    assert success and result["response"] == "Beside the sofa."
    print("CONTRACT Central-LLM PASS path=/api/v1/generate response=text mapped=response system_prompt=absent")
