"""Restrict explicit face-evidence retention to the ignored diagnostic tree."""

from pathlib import Path

DIAGNOSTIC_ROOT = Path(__file__).resolve().parents[1] / "logs" / "face-validation"


def diagnostic_directory(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(DIAGNOSTIC_ROOT.resolve()):
        raise ValueError("Face evidence must be retained under logs/face-validation")
    return resolved
