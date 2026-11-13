"""Cria snapshot revisavel sem .git, sem commit e sem alterar o repositorio original."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

from audit_sharing import ROOT, candidates, git

DIRECTORIES = {"backend", "catalog_expansion", "config", "data_mining", "docs", "frontend",
               "messaging", "migrations", "ops", "scraping", "scripts", "tests", ".github"}
FILES = {".dockerignore", ".env.example", ".gitattributes", ".gitignore", "AGENTS.md", "LICENSE",
         "README.md", "CONTRIBUTING.md", "Dockerfile", "Dockerfile.test", "pyproject.toml",
         "requirements.txt", "requirements-dev.txt", "compose.yaml", "compose.app.yaml",
         "compose.dev.yaml", "compose.team-test.yaml", "compose.simulation.yaml", "app.py", "auth.py", "serve_frontend.py"}
DENIED = {".git", ".secrets", "secrets", "__pycache__", "local-reports", "backups", "local-data", ".venv"}
SUFFIXES = {".dpapi", ".pem", ".key", ".pfx", ".p12", ".crt", ".cer", ".der", ".dump", ".backup",
            ".bak", ".log", ".zip", ".sqlite", ".db", ".pyc", ".jks", ".keystore"}


def allowed(name):
    p = Path(name)
    if any(part in DENIED for part in p.parts) or p.suffix.lower() in SUFFIXES:
        return False
    if p.name.startswith(".env") and name != ".env.example":
        return False
    if p.name in ("id_rsa", "id_ed25519") or p.name.startswith(("credentials", "service-account")):
        return False
    return name in FILES or (p.parts[0] in DIRECTORIES and not (ROOT / p).is_symlink())


def historical_secrets():
    found = set()
    for line in git("rev-list", "--objects", "--all").decode().splitlines():
        oid, _, _ = line.partition(" ")
        if git("cat-file", "-t", oid).strip() != b"blob":
            continue
        data = git("cat-file", "blob", oid)
        for match in re.finditer(rb"(?:postgres(?:ql)?|amqps?)://[^\s/:]+:([^\s/@{}]+)@", data):
            found.add(match[1])
        for match in re.finditer(rb"(?:SECRET_KEY|JWT_SECRET_KEY)\s*=\s*['\"]([^'\"\r\n]+)['\"]", data):
            found.add(match[1])
    return {v for v in found if len(v) >= 8}


def main():
    payload = {}
    for name in candidates():
        if allowed(name):
            payload[name] = (ROOT / name).read_bytes()
    # Continuidade operacional privada continua intacta no original.
    payload["CONTINUIDADE.md"] = (
        "# Hunter ? continuidade da equipe\n\n"
        "Snapshot sem historico Git. Consulte README.md, CONTRIBUTING.md e docs/COMPARTILHAMENTO.md.\n"
        "Banco novo via scripts/dev.py; nenhum usuario, cofre, backup ou segredo do operador foi copiado.\n"
        "Nao publicar o historico do repositorio original. Nenhum commit/push foi criado por esta preparacao.\n"
    ).encode("utf-8")
    secrets = historical_secrets()
    rejected = [name for name, data in payload.items() if any(value in data for value in secrets)]
    if rejected:
        raise ValueError("Snapshot recusado: referencia a segredo historico em " + ", ".join(rejected))
    required = ["backend/main.py", "frontend/index.html", "migrations/005_rotacao_multiloja.sql",
                "migrations/006_lojas_tecnologia.sql",
                "ops/base_schema.sql", "compose.dev.yaml", "scripts/dev.py", "requirements.txt", ".env.example"]
    if any(name not in payload for name in required):
        raise ValueError("Snapshot incompleto")
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())}
    payload["SHARE_MANIFEST.json"] = json.dumps(manifest, indent=2).encode()
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = output / ("hunter-share-" + stamp + ".zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(payload.items()):
            z.writestr("Hunter/" + name, data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".sha256").write_text(digest + "  " + archive.name + "\n", encoding="utf-8")
    print(f"Snapshot preparado: dist/{archive.name}; {len(manifest)} arquivos + manifesto; sem .git/segredos historicos.")


if __name__ == "__main__":
    main()
