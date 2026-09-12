import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.ssl_config import client_verify
from shared.security import internal_service_headers


def _get_base_urls() -> tuple[str, str]:
    enrollment_url = os.getenv("ENROLLMENT_SERVICE_URL", "https://localhost:8005")
    central_url = os.getenv("CENTRAL_SERVER_URL", "https://localhost:8000")
    return enrollment_url.rstrip("/"), central_url.rstrip("/")


def _build_payload(enrollment_data: Dict[str, Any]) -> Dict[str, Any]:
    name = enrollment_data.get("user_name") or enrollment_data.get("name") or ""
    payload = {
        "name": name,
        "user_name": name,
        "user_id": enrollment_data.get("user_id"),
        "face_embeddings": enrollment_data.get("face_embeddings", []),
        "voice_embeddings": enrollment_data.get("voice_embeddings", []),
        "age": enrollment_data.get("age"),
        "relation": enrollment_data.get("relation"),
        "avg_face_confidence": enrollment_data.get("avg_face_confidence"),
        "avg_voice_quality": enrollment_data.get("avg_voice_quality"),
        "enrollment_timestamp": enrollment_data.get("enrollment_timestamp"),
    }
    return payload


def _sync_user(client: httpx.Client, enrollment_url: str, central_url: str, user_id: str) -> Dict[str, Any]:
    enrollment_resp = client.get(f"{enrollment_url}/enrollment/storage/{user_id}")
    enrollment_resp.raise_for_status()
    enrollment_data = enrollment_resp.json().get("enrollment_data", {})
    payload = _build_payload(enrollment_data)

    name = payload.get("name")
    if not name:
        return {"user_id": user_id, "status": "skipped", "reason": "missing name"}

    check_resp = client.get(f"{central_url}/users/check", params={"name": name})
    if check_resp.status_code == 200 and check_resp.json().get("exists"):
        return {"user_id": user_id, "status": "skipped", "reason": "already exists"}

    add_resp = client.post(f"{central_url}/users", json=payload)
    add_resp.raise_for_status()
    return {"user_id": user_id, "status": "synced"}


def main() -> int:
    enrollment_url, central_url = _get_base_urls()

    with httpx.Client(timeout=30.0, verify=client_verify(), headers=internal_service_headers()) as client:
        list_resp = client.get(f"{enrollment_url}/enrollment/storage/list")
        list_resp.raise_for_status()
        user_ids: List[str] = list_resp.json().get("user_ids", [])

        if not user_ids:
            print("No enrollment users found to sync.")
            return 0

        results = []
        for user_id in user_ids:
            try:
                results.append(_sync_user(client, enrollment_url, central_url, user_id))
            except Exception as exc:
                results.append({"user_id": user_id, "status": "error", "reason": str(exc)})

    summary = {
        "total": len(results),
        "synced": sum(1 for r in results if r["status"] == "synced"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
