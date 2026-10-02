"""REST-only multi-angle diagnostics; private retention requires explicit opt-in."""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import shutil
import sys
import time
import tempfile
from uuid import uuid4

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
load_dotenv(ROOT / ".env", override=False)

from shared.face_diagnostics import diagnostic_directory
import test as console_module
from test import _capture_face_samples, _capture_validated_face_samples, _capture_voice_samples, LiveRESTClient, Sprint2Console, _safe_payload


ANGLES = ("front", "left", "right", "up", "down")
logger = logging.getLogger(__name__)


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if not 5 <= len(rows) <= 10:
        raise ValueError("Supply 5-10 real photos of one person")
    if {row.get("angle") for row in rows} != set(ANGLES):
        raise ValueError("Manifest must include front, left, right, up, and down")
    for row in rows:
        photo = Path(row["path"])
        if not photo.is_absolute():
            photo = path.parent / photo
        if not photo.is_file():
            raise ValueError(f"Photo does not exist: {photo}")
        row["path"] = str(photo.resolve())
    return rows


async def evaluate(rows: list[dict[str, str]], client: Sprint2Console) -> list[dict]:
    """Only orchestrate Enrollment's authenticated production REST endpoint."""
    results = []
    for row in rows:
        started = time.perf_counter()
        result = {"angle": row["angle"], "path": row["path"], "detected": None,
                  "confidence": None, "embedding_generated": False, "error": None}
        try:
            response = await asyncio.to_thread(client.validate_photo, Path(row["path"]))
            body = response.body
            face = body if response.ok else body.get("error", {}).get("validation", {})
            if not isinstance(face, dict):
                face = {}
            result.update(valid=response.ok and face.get("valid", False),
                          detected=face.get("face_detected"), confidence=face.get("confidence"),
                          embedding_generated=face.get("embedding_generated", False),
                          reason=face.get("reason"), status_code=response.status_code,
                          error=None if response.ok else console_module._response_message(body, "Photo validation request failed"))
        except Exception as exc:
            result.update(error="Photo validation request failed", reason="REQUEST_FAILURE", error_type=type(exc).__name__)
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        results.append(result)
    return results


def report_table(results: list[dict]) -> str:
    lines = ["| Angle | Face detected | Confidence | Embedding | REST ms | Error |",
             "|---|---|---:|---|---:|---|"]
    for row in results:
        detected = "unknown" if row["detected"] is None else str(row["detected"]).lower()
        confidence = "n/a" if row["confidence"] is None else f"{row['confidence']:.4f}"
        error = str(row["error"] or "-").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['angle']} | {detected} | {confidence} | "
                     f"{'yes' if row['embedding_generated'] else 'no'} | {row['elapsed_ms']:.2f} | {error} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--capture", action="store_true", help="Use test.py's existing SPACE/ESC webcam capture")
    source.add_argument("--parallel-capture", action="store_true", help="Exercise the real background REST validation and numbered retakes")
    source.add_argument("--manifest", type=Path, help="CSV with angle,path; paths may be relative to the CSV")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "logs" / "face-validation", help="Must be under logs/face-validation")
    parser.add_argument("--retain-artifacts", action="store_true", help="Opt in to retaining private photos/logs; default deletes on exit")
    parser.add_argument("--person-label", required=True, help="Anonymous label for the single person supplying all photos")
    parser.add_argument("--bad-photo-number", type=int, choices=range(1, len(ANGLES) + 1),
                        help="Ask for a turned-away photo at this number, then a normal retake (parallel capture only)")
    parser.add_argument("--reproduce-enrollment-error", action="store_true",
                        help="Record five real voice clips and submit a known rejected five-photo set through test.py's REST upload")
    parser.add_argument("--benchmark-background", action="store_true",
                        help="Replay a good five-photo manifest at its recorded file timestamps through the real background REST flow")
    args = parser.parse_args(argv)
    output_root = diagnostic_directory(args.output_dir)
    if args.bad_photo_number is not None and not args.parallel_capture:
        parser.error("--bad-photo-number requires --parallel-capture")
    rest_client = LiveRESTClient()
    client = Sprint2Console(rest_client)
    base_url = rest_client.urls.enrollment
    if not base_url.lower().startswith("https://"):
        raise ValueError("Face diagnostics require the existing HTTPS service URL")
    if not rest_client.request("enrollment", "GET", "/health", display=False, quiet=True).ok:
        rest_client.close()
        raise RuntimeError("Enrollment is not healthy/reachable; start Enrollment and Vision before capture")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = None if args.retain_artifacts else tempfile.TemporaryDirectory(prefix="faces-", dir=output_root)
    run_dir = Path(temporary.name) if temporary else output_root / f"faces-{stamp}-{uuid4().hex[:8]}"
    photos_dir = run_dir / "photos"
    photos_dir.mkdir(parents=True)
    handler = logging.FileHandler(run_dir / "diagnostic.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    print(f"Artifacts {'retained' if args.retain_artifacts else 'temporary; deleted on exit'} at: {run_dir}", flush=True)
    try:
        timings = {}
        if args.parallel_capture:
            rest = LiveRESTClient()
            attempts = []
            console = Sprint2Console(rest)
            original_validate = console.validate_photo

            def record_validation(path):
                started = time.perf_counter()
                response = original_validate(path)
                attempts.append({"photo": path.name, "http_status": response.status_code,
                                 "result": response.body, "rest_ms": (time.perf_counter() - started) * 1000})
                return response

            console.validate_photo = record_validation
            try:
                if not rest.request("enrollment", "GET", "/health", display=False).ok:
                    raise RuntimeError("Enrollment must be running for parallel capture")
                guidance = {args.bad_photo_number: "turn fully away (test)"} if args.bad_photo_number else None
                paths = _capture_validated_face_samples(console, photos_dir, count=len(ANGLES),
                                                       guidance=guidance, timing_report=timings)
            finally:
                (run_dir / "validation-attempts.json").write_text(json.dumps(attempts, indent=2), encoding="utf-8")
                rest.close()
            rows = [{"angle": angle, "path": str(path)} for angle, path in zip(ANGLES, paths)]
        elif args.capture:
            print("Use ONE person: front, slight left/right/up/down. SPACE captures; ESC cancels.", flush=True)
            paths = _capture_face_samples(photos_dir, count=len(ANGLES))
            rows = [{"angle": angle, "path": str(path)} for angle, path in zip(ANGLES, paths)]
        else:
            rows = read_manifest(args.manifest.resolve())
            for index, row in enumerate(rows, 1):
                original = Path(row["path"])
                retained = photos_dir / f"{index}-{row['angle']}{original.suffix}"
                shutil.copy2(original, retained)
                row["path"] = str(retained)
        fingerprints = [hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() for row in rows]
        if len(set(fingerprints)) != len(rows):
            raise ValueError("Repeated identical images cannot serve as distinct angle evidence")
        with (run_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=("angle", "path"))
            writer.writeheader()
            writer.writerows({"angle": row["angle"], "path": str(Path(row["path"]).relative_to(run_dir))} for row in rows)
        results = asyncio.run(evaluate(rows, client))
        report = {"person_label": args.person_label, "source": "user-supplied real photos",
                  "enrollment_url": base_url, "check": "POST /enrollment/validate-photo",
                  "photo_sha256": fingerprints, "results": results,
                  "capture_timings": timings,
                  "limitation": "Small per-person sample; this cannot establish population-level pose accuracy."}
        (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        table = report_table(results)
        (run_dir / "report.md").write_text(table + "\n\n" + report["limitation"] + "\n", encoding="utf-8")
        print(table, flush=True)
        if args.benchmark_background:
            if args.manifest is None or len(rows) != len(ANGLES) or not all(row["embedding_generated"] for row in results):
                raise ValueError("Background timing needs a passing five-photo manifest")
            stamps = [Path(row["path"]).stat().st_mtime for row in rows]
            offsets = [stamp - stamps[0] for stamp in stamps]
            if offsets != sorted(offsets):
                raise ValueError("Timing manifest must preserve the original capture order/timestamps")
            metrics = {}
            rest = LiveRESTClient()
            original_capture = console_module._capture_face_samples

            def replay(output_dir, count, photo_numbers, on_capture, guidance):
                if photo_numbers != list(range(1, len(rows) + 1)):
                    raise RuntimeError("A previously passing frame failed during replay; inspect the retained service log")
                started = time.perf_counter()
                paths = []
                for number in photo_numbers:
                    time.sleep(max(0, offsets[number - 1] - (time.perf_counter() - started)))
                    path = Path(rows[number - 1]["path"])
                    paths.append(path)
                    on_capture(number, path)
                return paths

            try:
                console_module._capture_face_samples = replay
                _capture_validated_face_samples(Sprint2Console(rest), photos_dir, count=len(ANGLES), timing_report=metrics)
            finally:
                console_module._capture_face_samples = original_capture
                rest.close()
            comparison = {"kind": "Real-image REST replay using original capture timestamps; not a second live camera run",
                          "capture_span_seconds": offsets[-1],
                          "sequential_validation_seconds": sum(row["elapsed_ms"] for row in results) / 1000,
                          "sequential_total_seconds": offsets[-1] + sum(row["elapsed_ms"] for row in results) / 1000,
                          "background": metrics,
                          "cache_note": "Sequential checks now populate Enrollment cache; background replay may reuse them. Not an uncached speedup benchmark."}
            (run_dir / "timing-comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
            print(json.dumps(comparison, indent=2), flush=True)
        if args.reproduce_enrollment_error:
            if len(rows) != len(ANGLES) or not any(row["detected"] is False for row in results):
                raise ValueError("Error reproduction requires exactly five photos including a confirmed no-face frame")
            print("Record five real voice clips next. Enrollment should reject the known bad photo before voice embedding/storage.", flush=True)
            voice_dir = run_dir / "voice"
            voice_dir.mkdir()
            voices = _capture_voice_samples(voice_dir)
            rest = LiveRESTClient()
            try:
                console = Sprint2Console(rest)
                response = console._upload_samples("/enrollment/enroll", [Path(row["path"]) for row in rows],
                                                   voices, "photos", "voice_samples", {"user_name": args.person_label})
                (run_dir / "enrollment-response.json").write_text(
                    json.dumps({"http_status": response.status_code, "body": _safe_payload(response.body)}, indent=2), encoding="utf-8")
                if response.ok:
                    raise RuntimeError("Known-bad enrollment unexpectedly succeeded; inspect its response before cleanup")
                print(f"Actual enrollment rejection saved: HTTP {response.status_code}", flush=True)
            finally:
                rest.close()
        return 0 if all(row["embedding_generated"] for row in results) else 1
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()
        rest_client.close()
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
