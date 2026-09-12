"""Generate reproducible OpenAPI documents from the seven authoritative apps."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs" / "openapi"
SERVICES = {
    "central": ("01_central_server", "main", 8000),
    "vision": ("02_vision_service", "vision_service.app", 8001),
    "audio": ("03_audio_service", "main", 8002),
    "tts": ("04_tts_service", "tts_service.app", 8003),
    "teachme": ("05_teachme_service", "teachme_service.app", 8004),
    "enrollment": ("06_enrollment_service", "app.main", 8005),
    "llm": ("07_llm_service", "main", 8006),
}


def _load_schema(service: str) -> dict:
    directory, module_name, port = SERVICES[service]
    service_dir = ROOT / directory
    sys.path[:0] = [str(ROOT), str(service_dir)]
    module = importlib.import_module(module_name)
    schema = module.app.openapi()
    schema["servers"] = [{"url": f"https://localhost:{port}", "description": "Local service (TLS)"}]
    return schema


def _child(service: str) -> None:
    print(json.dumps(_load_schema(service), separators=(",", ":"), ensure_ascii=True))


def generate_all() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    schemas: dict[str, dict] = {}
    for service, (directory, _, _) in SERVICES.items():
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--service", service],
            cwd=ROOT / directory,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(f"OpenAPI generation failed for {service}:\n{result.stderr}")
        schema = json.loads(result.stdout.strip().splitlines()[-1])
        schemas[service] = schema
        destination = OUTPUT_DIR / f"{service}.json"
        destination.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"GENERATED {service:10} paths={len(schema.get('paths', {})):3} {destination.relative_to(ROOT)}")

    # Retain the historical path as a generated compatibility artifact, now
    # representing the authoritative Central application exactly.
    (ROOT / "docs" / "openapi.yaml").write_text(
        yaml.safe_dump(schemas["central"], sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print("GENERATED central-yaml docs/openapi.yaml")

    old_result = subprocess.run(
        ["git", "show", "HEAD:docs/openapi.yaml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    old_schema = yaml.safe_load(old_result.stdout)
    old_paths = set(old_schema.get("paths", {}))
    current_paths = set(schemas["central"].get("paths", {}))
    print(f"SPEC_DIFF old_paths={len(old_paths)} generated_central_paths={len(current_paths)}")
    print(f"OLD_ONLY={sorted(old_paths - current_paths)}")
    print(f"MISSING_FROM_OLD={sorted(current_paths - old_paths)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=SERVICES)
    args = parser.parse_args()
    if args.service:
        _child(args.service)
    else:
        generate_all()


if __name__ == "__main__":
    main()
