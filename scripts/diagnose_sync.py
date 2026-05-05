import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "06_enrollment_service"))

from app.utils.storage_adapter import get_storage_adapter


def main() -> None:
    os.environ.setdefault("ENCRYPTION_KEY_FILE", "./06_enrollment_service/encryption.key")
    storage = get_storage_adapter(
        "./06_enrollment_service/enrollment_data",
        True,
        use_async=False,
    )

    user_ids = storage.list_enrollments()
    missing = []
    errors = []

    for user_id in user_ids:
        try:
            data = storage.get_enrollment(user_id)
            if not data:
                missing.append((user_id, "no_data"))
                continue
            name = data.get("user_name") or data.get("name")
            if not name:
                missing.append((user_id, "missing_name"))
        except Exception as exc:
            errors.append((user_id, str(exc)))

    print("total", len(user_ids), "missing", len(missing), "errors", len(errors))
    if missing:
        print("missing", missing[:10])
    if errors:
        print("errors", errors[:10])


if __name__ == "__main__":
    main()
