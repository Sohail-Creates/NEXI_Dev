"""Read-only runtime audit: fresh per-service installs, real imports, HTTPS health.

Run with the existing development interpreter. Each target environment receives
only its service manifest. Runtime data and test credentials are temporary; no
production store or real credential is changed. Stop at the first failed check.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import secrets
import re
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cryptography.fernet import Fernet
import httpx
from config.ssl_config import generate_local_certificates

SERVICES = (
    ("Central", "01_central_server", "main:app", "/health", 8000),
    ("Vision", "02_vision_service", "vision_service.app:app", "/health", 8001),
    ("Audio", "03_audio_service", "main:app", "/health", 8002),
    ("TTS", "04_tts_service", "tts_service.app:app", "/health", 8003),
    ("TeachMe", "05_teachme_service", "teachme_service.app:app", "/health", 8004),
    ("Enrollment", "06_enrollment_service", "app.main:app", "/health", 8005),
    ("LLM", "07_llm_service", "main:app", "/api/v1/health", 8006),
)


def import_inventory() -> None:
    """Trace local imports from actual entrypoints; report, never auto-remove pins.

    AST reachability includes imports inside functions/optional branches. A pin
    absent here can still be a dependency of a third-party runtime package; the
    output deliberately calls it a review candidate, not a safe deletion.
    """
    aliases = {"dotenv": "python-dotenv", "cv2": "opencv-python",
               "jwt": "pyjwt", "PIL": "pillow", "sklearn": "scikit-learn",
               "multipart": "python-multipart", "yaml": "pyyaml",
               "pyaudio": "pyaudio", "piper": "piper-tts",
               "av": "av", "webrtcvad": "webrtcvad-wheels"}
    def candidate(base: Path, module: str) -> Path | None:
        path = base.joinpath(*module.split(".")) if module else base
        for choice in (path.with_suffix(".py"), path / "__init__.py"):
            if choice.is_file():
                return choice
        return None
    for name, app_dir, target, _health, _port in SERVICES:
        service_root = ROOT / app_dir
        pending = [candidate(service_root, target.split(":")[0])]
        seen, external = set(), set()
        while pending:
            path = pending.pop()
            if path is None or path in seen:
                continue
            seen.add(path)
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [(alias.name, 0) for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [(node.module or "", node.level)]
                    modules += [((node.module + "." if node.module else "") + alias.name,
                                 node.level) for alias in node.names]
                else:
                    continue
                for module, level in modules:
                    if level:
                        base = path.parent
                        for _ in range(level - 1):
                            base = base.parent
                        resolved = candidate(base, module)
                    else:
                        resolved = candidate(service_root, module) or candidate(ROOT, module)
                    if resolved:
                        pending.append(resolved)
                        # Python executes package initializers before submodules;
                        # config.__init__ is why settings is required by TLS.
                        parent = resolved.parent
                        while parent != ROOT and ROOT in parent.parents:
                            initializer = parent / "__init__.py"
                            if initializer.is_file():
                                pending.append(initializer)
                            parent = parent.parent
                    elif not level and module:
                        top = module.split(".")[0]
                        local_top = (candidate(service_root, top) or candidate(ROOT, top)
                                     or (service_root / top).is_dir() or (ROOT / top).is_dir())
                        if not local_top and top not in sys.stdlib_module_names:
                            external.add(top)
        imported = {aliases.get(module, module.replace("_", "-")).casefold()
                    for module in external}
        declared = []
        for line in (service_root / "requirements.txt").read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                declared.append(re.split(r"[\[<>=!~ ]", line.strip(), maxsplit=1)[0].casefold())
        print("IMPORT_GRAPH " + json.dumps({
            "service": name, "entrypoint": target, "local_modules": len(seen),
            "external_imports_including_optional": sorted(external),
            "manifest_review_candidates_not_proven_unused": sorted(set(declared) - imported),
        }), flush=True)


def isolated_regression(venv_name: str) -> int:
    """Run existing assertions, choosing isolated interpreters for real servers.

    Older fixtures hard-code the monolithic development interpreter. This
    opt-in, scoped launcher adaptation changes only ``python -m uvicorn``
    executable selection for the seven authoritative app directories. Custom
    fixture servers and all test assertions remain untouched.
    """
    import pytest

    interpreters = {directory: ROOT / directory / venv_name / "Scripts" / "python.exe"
                    for _name, directory, _target, _health, _port in SERVICES}
    for python in interpreters.values():
        if not python.is_file():
            raise RuntimeError(f"isolated regression requires audited environment: {python}")
    original_popen = subprocess.Popen
    def isolated_popen(args, *positional, **kwargs):
        if isinstance(args, (list, tuple)):
            command = list(args)
            if command[1:3] == ["-m", "uvicorn"] and "--app-dir" in command:
                app_dir = Path(command[command.index("--app-dir") + 1]).resolve()
                if app_dir.parent == ROOT and app_dir.name in interpreters:
                    command[0] = str(interpreters[app_dir.name])
                    print("ISOLATED_TEST_SERVER " + subprocess.list2cmdline(command), flush=True)
                    args = command
        return original_popen(args, *positional, **kwargs)
    # Same explicit inference-thread configuration used in the live install
    # audit, not a hardware lease or a relaxation of startup/HTTP deadlines.
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"
    with tempfile.TemporaryDirectory(prefix="nexi-native-regression-") as directory:
        temporary = Path(directory)
        environment = {
            "AUDIO_DATA_DIR": str(temporary / "audio"),
            "AUDIO_QUEUE_DB_PATH": str(temporary / "audio-queue.sqlite3"),
            "VAD_RECORDING_OUTPUT_DIR": str(temporary / "recordings"),
            "OBJECT_DETECTION_MODEL": str(ROOT / "02_vision_service" / "yolov8n"),
            "MPLCONFIGDIR": str(temporary / "matplotlib"),
        }
        with pytest.MonkeyPatch.context() as patch:
            for key, value in environment.items():
                patch.setenv(key, value)
            patch.setattr(subprocess, "Popen", isolated_popen)
            return int(pytest.main([
                "-x", "-v", "-s",
                "tests/test_phase4.py", "tests/test_phase5.py", "tests/test_phase6.py",
                "tests/test_phase7_cloud_sync.py", "tests/test_route_naming_normalization.py",
                "tests/test_phase8_unit.py", "tests/test_phase8_contracts.py",
                "tests/test_phase8_e2e.py", "tests/test_phase8_resilience.py",
                "tests/phase9_security_verification.py",
                "--junitxml=logs/final-native-isolated-regression.xml",
                "-o", "junit_logging=all",
            ]))


def checked(command: list[str], environment: dict[str, str]) -> str:
    print("COMMAND " + subprocess.list2cmdline(command), flush=True)
    with subprocess.Popen(command, cwd=ROOT, env=environment,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, errors="replace", bufsize=1) as process:
        output = []
        for line in process.stdout:
            output.append(line)
            print(line, end="", flush=True)
        returncode = process.wait()
    print(f"EXIT_CODE={returncode}", flush=True)
    if returncode:
        raise RuntimeError(f"command failed with exit {returncode}")
    return "".join(output).strip()


def audit(service: tuple, venv_name: str, directory: Path) -> dict:
    name, app_dir, target, health_path, port = service
    manifest = ROOT / app_dir / "requirements.txt"
    row = {"service": name, "install_exit_code": "NOT RUN",
           "pip_check": "NOT RUN", "real_import": "NOT RUN",
           "health_http_status": "NOT RUN", "health_body": "NOT RUN"}
    process = None
    log_path = directory / f"{name.lower()}-startup.log"
    try:
        if not manifest.is_file():
            raise RuntimeError(f"missing service manifest: {manifest}")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
        venv = ROOT / app_dir / venv_name
        if venv.exists():
            raise RuntimeError(f"fresh environment required; choose another --venv-name: {venv}")
        tls = generate_local_certificates(directory / name / "tls")
        environment = os.environ.copy()
        environment.update({
            "PYTHONPATH": os.pathsep.join((str(ROOT), str(ROOT / app_dir))),
            "AUTH_ENFORCEMENT_ENABLED": "true",
            "NEXI_INTERNAL_SERVICE_TOKEN": secrets.token_urlsafe(32),
            "NEXI_JWT_SECRET": secrets.token_urlsafe(48),
            "NEXI_FERNET_KEY": Fernet.generate_key().decode(),
            "NEXI_TLS_ENABLED": "true", "NEXI_TLS_ALLOW_PLAINTEXT": "false",
            "NEXI_TLS_CERT_FILE": str(tls.cert_file),
            "NEXI_TLS_KEY_FILE": str(tls.key_file),
            "NEXI_TLS_CA_FILE": str(tls.ca_file),
            "CLOUD_SYNC_ENABLED": "false",
            "CENTRAL_DB_PATH": str(directory / name / "central.sqlite3"),
            "STORAGE_FILE": str(directory / name / "knowledge.json"),
            "BACKUP_DIR": str(directory / name / "knowledge-backups"),
            "ENROLLMENT_DATA_DIR": str(directory / name / "enrollment"),
            "SPEAKER_EMBEDDINGS_FILE": str(directory / name / "speakers.json"),
            "AUDIO_DATA_DIR": str(directory / name / "audio"),
            "AUDIO_QUEUE_DB_PATH": str(directory / name / "audio-queue.sqlite3"),
            "VAD_RECORDING_OUTPUT_DIR": str(directory / name / "recordings"),
            "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
            "MPLCONFIGDIR": str(directory / name / "matplotlib"),
            "OBJECT_DETECTION_MODEL": str(ROOT / "02_vision_service" / "yolov8n"),
        })
        checked([sys.executable, "-m", "venv", str(venv)], environment)
        python = str(venv / "Scripts" / "python.exe")
        print(f"ISOLATED_INTERPRETER={python}", flush=True)
        try:
            checked([python, "-m", "pip", "install", "-r", str(manifest)], environment)
            row["install_exit_code"] = 0
        except RuntimeError:
            row["install_exit_code"] = "NONZERO (see command output)"
            raise
        row["pip_check"] = checked([python, "-m", "pip", "check"], environment)
        if name == "Central":
            checked([python, str(ROOT / app_dir / "migrate_cloud_sync_outbox.py"),
                     "--database", environment["CENTRAL_DB_PATH"]], environment)
        if name == "TeachMe":
            checked([python, "-c", "from pathlib import Path; "
                     "from teachme_service.sqlite_store import initialize; "
                     f"initialize(Path({environment['STORAGE_FILE']!r}).with_suffix('.sqlite3')); "
                     "print('TEACHME_SCHEMA_INITIALIZED=PASS')"], environment)
        module, attribute = target.split(":")
        row["real_import"] = "FAIL (see real app import output)"
        row["real_import"] = checked(
            [python, "-c", f"from {module} import {attribute}; print('REAL_APP_IMPORT=PASS')"],
            environment)
        if name == "Central":
            checked([python, "-c", "from shared.semantic_embeddings import "
                     "embed_text, SEMANTIC_EMBEDDING_DIMENSION; "
                     "vector = embed_text('NEXI readiness'); "
                     "assert len(vector) == SEMANTIC_EMBEDDING_DIMENSION; "
                     "print('CENTRAL_SEMANTIC_DIMENSION=' + str(len(vector)))"],
                    environment)
        command = [python, "-m", "uvicorn", target, "--app-dir", str(ROOT / app_dir),
                   "--host", "127.0.0.1", "--port", str(port), "--log-level", "info",
                   "--ssl-certfile", str(tls.cert_file), "--ssl-keyfile", str(tls.key_file)]
        print("START_COMMAND " + subprocess.list2cmdline(command), flush=True)
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=ROOT, env=environment,
                                       stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 120
            with httpx.Client(verify=str(tls.ca_file), trust_env=False, timeout=15) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f"startup exited with {process.returncode}")
                    try:
                        response = client.get(f"https://127.0.0.1:{port}{health_path}")
                        row["health_http_status"] = response.status_code
                        row["health_body"] = response.text
                        if response.status_code == 200:
                            if response.json().get("status") not in {"healthy", "degraded"}:
                                raise RuntimeError("health body is not healthy or honestly degraded")
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("health readiness deadline exceeded")
        row["venv"] = str(venv)
        return row
    except Exception as exc:
        row["failure"] = str(exc)
        raise
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if log_path.exists():
            print("STARTUP_LOG_BEGIN", flush=True)
            print(log_path.read_text(encoding="utf-8", errors="replace"), flush=True)
            print("STARTUP_LOG_END", flush=True)
        print("AUDIT_ROW " + json.dumps(row), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=[item[0] for item in SERVICES])
    parser.add_argument("--venv-name", default="venv-audit-01")
    parser.add_argument("--imports", action="store_true", help="read-only entrypoint import graph")
    parser.add_argument("--regression", action="store_true", help="unchanged tests, isolated server interpreters")
    args = parser.parse_args()
    if args.imports:
        import_inventory()
        return 0
    if not args.venv_name.startswith("venv-audit-") or Path(args.venv_name).name != args.venv_name:
        parser.error("--venv-name must be a simple directory name starting with venv-audit-")
    if args.regression:
        return isolated_regression(args.venv_name)
    directory = Path(tempfile.mkdtemp(prefix="nexi-isolated-audit-"))
    print(f"AUDIT_RUNTIME_DIRECTORY={directory}", flush=True)
    try:
        for service in SERVICES:
            if not args.service or args.service == service[0]:
                audit(service, args.venv_name, directory)
    except Exception as exc:
        print(f"AUDIT_STOP={exc}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
