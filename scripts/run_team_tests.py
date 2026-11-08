"""Regressao Linux integral em namespace isolado, com saida nao mascarada."""
import subprocess
import sys


def main():
    commands = [
        ["-B", "-m", "messaging.testing"],
        ["-m", "ruff", "check", "."],
        ["-B", "-m", "coverage", "run", "-m", "unittest", "discover", "-s", "tests", "-v"],
        ["-m", "coverage", "report"],
        ["-B", "tests/demo_queue.py"],
        ["-B", "tests/browser_queue.py"],
        ["-B", "tests/browser_dashboard.py"],
    ]
    for args in commands:
        subprocess.run([sys.executable, *args], check=True)
    print("OK: regressao completa em banco/broker isolados sem credenciais locais.")


if __name__ == "__main__":
    main()
