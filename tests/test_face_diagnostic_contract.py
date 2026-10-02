"""The diagnostic is a REST orchestrator with opt-in, private retention."""

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import diagnose_enrollment_faces as diagnostic
from shared import face_diagnostics
import test as console_module

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_diagnostic_preserves_reason_and_never_mislabels_decode_failure():
    client = SimpleNamespace(validate_photo=lambda path: console_module.LiveResponse(
        status_code=400, headers={}, raw=b"", body={"error": {
            "message": "Invalid image file", "validation": {"valid": False,
            "face_detected": None, "confidence": None, "embedding_generated": False,
            "reason": "INVALID_IMAGE"}}}))
    result = (await diagnostic.evaluate([{"angle": "left", "path": "bad.jpg"}], client))[0]
    assert result["reason"] == "INVALID_IMAGE"
    assert result["detected"] is None
    assert result["error"] == "Invalid image file"


@pytest.mark.parametrize("retain", [False, True])
def test_diagnostic_retention_is_explicit_and_reports_no_vectors(tmp_path, monkeypatch, retain):
    root = tmp_path / "private-diagnostics"
    monkeypatch.setattr(face_diagnostics, "DIAGNOSTIC_ROOT", root)
    manifest = tmp_path / "manifest.csv"
    with manifest.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=("angle", "path"))
        writer.writeheader()
        for angle in diagnostic.ANGLES:
            photo = tmp_path / f"{angle}.jpg"
            photo.write_bytes(angle.encode())
            writer.writerow({"angle": angle, "path": str(photo)})

    requests = []

    class REST:
        urls = SimpleNamespace(enrollment="https://enrollment.test")
        def request(self, service, method, path, **kwargs):
            requests.append((service, method, path, kwargs.get("internal")))
            return console_module.LiveResponse(status_code=200, headers={}, raw=b"", body={
                "valid": True, "face_detected": True, "confidence": 0.9,
                "embedding_generated": True, "reason": None})
        def close(self):
            pass

    monkeypatch.setattr(diagnostic, "LiveRESTClient", REST)
    args = ["--manifest", str(manifest), "--person-label", "anonymous", "--output-dir", str(root)]
    if retain:
        args.append("--retain-artifacts")
    assert diagnostic.main(args) == 0
    assert len(list(root.iterdir())) == int(retain)
    assert len([row for row in requests if row[2] == "/enrollment/validate-photo" and row[3] is True]) == 5
    if retain:
        report = next(root.glob("*/report.json")).read_text()
        assert '"embedding":' not in report
        assert '"token":' not in report
