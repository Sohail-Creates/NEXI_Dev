#!/usr/bin/env python
"""Audit every NEXI dependency manifest; fail closed on untriaged findings."""

from __future__ import annotations

import json
import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (
    ROOT / "requirements.txt",  # root/shared plus Audio's authoritative manifest
    ROOT / "01_central_server" / "requirements.txt",
    ROOT / "02_vision_service" / "requirements.txt",
    ROOT / "04_tts_service" / "requirements.txt",
    ROOT / "05_teachme_service" / "requirements.txt",
    ROOT / "06_enrollment_service" / "requirements.txt",
    ROOT / "07_llm_service" / "requirements.txt",
)


def audit(manifest: Path) -> tuple[list[dict], str | None]:
    command = [
        sys.executable, "-m", "pip_audit", "-r", str(manifest),
        "--format", "json", "--progress-spinner", "off",
    ]
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return [], "dependency resolution/audit exceeded 180 seconds; manifest NOT cleared"
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [], (result.stderr or result.stdout or f"pip-audit exit {result.returncode}").strip()
    if not isinstance(document, dict) or not isinstance(document.get("dependencies"), list):
        return [], "invalid pip-audit report schema; manifest NOT cleared"
    findings = []
    seen = set()
    for dependency in document.get("dependencies", []):
        for vulnerability in dependency.get("vulns", []):
            identity = (dependency.get("name"), dependency.get("version"), vulnerability.get("id"))
            if identity in seen:
                continue  # Identical advisory duplicates, not ignored vulnerabilities.
            seen.add(identity)
            findings.append({
                "package": dependency.get("name"),
                "version": dependency.get("version"),
                "id": vulnerability.get("id"),
                "fix_versions": vulnerability.get("fix_versions", []),
                # pip-audit's PyPI advisory response does not supply severity.
                # Fail closed instead of inventing or downgrading a score.
                "severity": "UNASSESSED_TREATED_AS_HIGH",
            })
    skipped = [dependency.get("name", "unknown") for dependency in document["dependencies"]
               if dependency.get("skip_reason")]
    error = f"unaudited/skipped packages: {', '.join(skipped)}; manifest NOT cleared" if skipped else None
    if result.returncode not in {0, 1}:
        error = (result.stderr or f"pip-audit exit {result.returncode}").strip()
    return findings, error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "logs/dependency-audit.json")
    args = parser.parse_args()
    report = {"policy": "fail_on_high_critical_or_unassessed", "manifests": []}
    print("NEXI DEPENDENCY VULNERABILITY SCAN", flush=True)
    print("policy=exit_nonzero_on_high_critical_or_unassessed severity_source=pip-audit/PyPI")
    total = 0
    errors = 0
    for manifest in MANIFESTS:
        relative = manifest.relative_to(ROOT)
        if not manifest.is_file():
            print(f"MANIFEST {relative} ERROR missing")
            errors += 1
            report["manifests"].append({"manifest": str(relative), "error": "missing", "findings": []})
            continue
        findings, error = audit(manifest)
        report["manifests"].append({"manifest": str(relative), "error": error, "findings": findings})
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if error:
            print(f"MANIFEST {relative} ERROR {error}", flush=True)
            errors += 1
        print(f"MANIFEST {relative} findings={len(findings)}", flush=True)
        for finding in findings:
            print(
                "  {package}=={version} {id} severity={severity} fixes={fixes}".format(
                    **finding, fixes=",".join(finding["fix_versions"]) or "none",
                )
            )
        total += len(findings)
    report.update({"findings": total, "errors": errors, "exit_code": 1 if total or errors else 0})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"REPORT {args.report}")
    print(f"SCAN_RESULT manifests={len(MANIFESTS)} findings={total} errors={errors} exit={'FAIL' if total or errors else 'PASS'}", flush=True)
    return 1 if total or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
