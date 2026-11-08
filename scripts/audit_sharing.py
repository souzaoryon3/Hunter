"""Audita arvore compartilhavel e todos os blobs historicos sem imprimir segredos."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# Heuristicas: achados exigem revisao; ausencia nao prova ausencia de segredos.
RULES = {
    "credential_url": re.compile(rb"(?:postgres(?:ql)?|amqps?|mongodb(?:\+srv)?)://[^\s/'\"]+:[^\s/@{}]+@", re.I),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9]{32,})"),
    "secret_assignment": re.compile(rb"(?:SECRET_KEY|JWT_SECRET_KEY|password|senha)\s*[:=]\s*['\"][^'\"\r\n]{4,}['\"]", re.I),
}


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def findings(data):
    return [name for name, pattern in RULES.items() if pattern.search(data)]


def candidates():
    raw = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted({p.decode("utf-8") for p in raw.split(b"\0") if p and (ROOT / p.decode("utf-8")).is_file()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    paths = candidates()
    working = [{"path": p, "rules": findings((ROOT / p).read_bytes())}
               for p in paths if findings((ROOT / p).read_bytes())]
    history = []
    if args.history:
        # Percorre todos os objetos alcan?aveis por refs, sem imprimir conteudo.
        objects = git("rev-list", "--objects", "--all").decode("utf-8", "replace").splitlines()
        for line in objects:
            oid, _, path = line.partition(" ")
            if git("cat-file", "-t", oid).strip() != b"blob":
                continue
            data = git("cat-file", "blob", oid)
            rules = findings(data)
            if rules:
                history.append({"object": oid, "path": path, "rules": rules})
    output = ROOT / "local-reports"
    output.mkdir(exist_ok=True)
    report = {"candidate_count": len(paths), "working_findings": working,
              "history_findings": history,
              "limitations": "Heuristicas; falsos positivos e falsos negativos possiveis. Valores nunca incluidos."}
    (output / "sharing-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"candidate_files": len(paths), "working_flagged": len(working),
                      "history_flagged_blobs": len(history),
                      "report": "local-reports/sharing-audit.json"}))


if __name__ == "__main__":
    main()
