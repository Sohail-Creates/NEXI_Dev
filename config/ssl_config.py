"""One TLS configuration for all NEXI service servers and clients."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CERT_DIR = ROOT / "config" / "certificates"
_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TLSConfig:
    enabled: bool
    cert_file: Path
    key_file: Path
    ca_file: Path
    plaintext_transition: bool

    @classmethod
    def from_env(cls) -> "TLSConfig":
        cert_dir = Path(os.getenv("NEXI_TLS_CERT_DIR", str(DEFAULT_CERT_DIR))).resolve()
        return cls(
            enabled=os.getenv("NEXI_TLS_ENABLED", "true").strip().lower() in _TRUE,
            cert_file=Path(os.getenv("NEXI_TLS_CERT_FILE", str(cert_dir / "nexi-local.crt"))).resolve(),
            key_file=Path(os.getenv("NEXI_TLS_KEY_FILE", str(cert_dir / "nexi-local.key"))).resolve(),
            ca_file=Path(os.getenv("NEXI_TLS_CA_FILE", str(cert_dir / "nexi-local-ca.crt"))).resolve(),
            plaintext_transition=os.getenv("NEXI_TLS_ALLOW_PLAINTEXT", "false").strip().lower() in _TRUE,
        )

    def validate(self) -> None:
        if not self.enabled:
            return
        missing = [str(path) for path in (self.cert_file, self.key_file, self.ca_file) if not path.is_file()]
        if missing:
            raise RuntimeError("TLS is enabled but certificate material is missing: " + ", ".join(missing))

    def uvicorn_kwargs(self) -> dict[str, str]:
        self.validate()
        return {"ssl_certfile": str(self.cert_file), "ssl_keyfile": str(self.key_file)} if self.enabled else {}


def get_tls_config() -> TLSConfig:
    return TLSConfig.from_env()


def client_verify(url: str | None = None) -> bool | str:
    """Return a trusted CA path for HTTPS; never permit verify=False."""
    if url is not None and not url.lower().startswith("https://"):
        return True
    config = get_tls_config()
    if config.enabled:
        if not config.ca_file.is_file():
            raise RuntimeError(f"TLS trust bundle is missing: {config.ca_file}")
        return str(config.ca_file)
    return True


def client_ssl_context(url: str | None = None) -> ssl.SSLContext | None:
    if url is not None and not url.lower().startswith("https://"):
        return None
    verify = client_verify(url)
    return ssl.create_default_context(cafile=verify) if isinstance(verify, str) else ssl.create_default_context()


def generate_local_certificates(cert_dir: Path = DEFAULT_CERT_DIR) -> TLSConfig:
    """Generate a self-signed local CA and a CA-verified localhost certificate."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_key_path = cert_dir / "nexi-local-ca.key"
    ca_cert_path = cert_dir / "nexi-local-ca.crt"
    key_path = cert_dir / "nexi-local.key"
    cert_path = cert_dir / "nexi-local.crt"
    now = datetime.now(timezone.utc)

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NEXI Local Verification CA")])
    ca_cert = (
        x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    service_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    service_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    sans = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    sans.extend(x509.DNSName(name) for name in ("central", "vision", "audio", "tts", "teachme", "enrollment", "llm"))
    service_cert = (
        x509.CertificateBuilder().subject_name(service_name).issuer_name(ca_name)
        .public_key(service_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    no_encryption = serialization.NoEncryption()
    ca_key_path.write_bytes(ca_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, no_encryption))
    ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(service_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, no_encryption))
    cert_path.write_bytes(service_cert.public_bytes(serialization.Encoding.PEM))
    for path in (ca_key_path, key_path):
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return TLSConfig(True, cert_path, key_path, ca_cert_path, False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate-local", action="store_true")
    parser.add_argument("--cert-dir", type=Path, default=DEFAULT_CERT_DIR)
    args = parser.parse_args()
    if args.generate_local:
        generated = generate_local_certificates(args.cert_dir.resolve())
        print(f"TLS_CA={generated.ca_file}")
        print(f"TLS_CERT={generated.cert_file}")
        print(f"TLS_KEY={generated.key_file}")
