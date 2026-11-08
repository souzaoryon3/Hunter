"""Sintaxe Python/JS e deteccao basica de literais; nao imprime valores encontrados."""

import ast
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    findings = []
    count = 0
    for folder in (
        "backend",
        "config",
        "messaging",
        "catalog_expansion",
        "data_mining",
        "scraping",
        "scripts",
        "ops",
        "tests",
    ):
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            count += 1
            if folder == "tests":
                continue  # URLs sinteticas explicitas de testes negativos.
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if re.search(r"postgres(?:ql)?://[^\s/]+:[^\s/@{}]+@", node.value):
                        findings.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: DSN literal com senha"
                        )
                if (
                    isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    if any(
                        isinstance(t, ast.Name)
                        and t.id in ("SECRET_KEY", "JWT_SECRET_KEY")
                        for t in node.targets
                    ):
                        findings.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: segredo literal"
                        )
    for path in (ROOT / "frontend/assets/js").rglob("*.js"):
        subprocess.run(["node", "--check", str(path)], check=True)
    if findings:
        raise ValueError(
            "Literais sensiveis detectados (valores omitidos): " + "; ".join(findings)
        )
    print(
        f"Qualidade basica aprovada: {count} modulos Python, JavaScript e ausencia de DSN/segredo literal nas atribuicoes verificadas."
    )


if __name__ == "__main__":
    main()
