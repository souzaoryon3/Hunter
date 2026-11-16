"""Entrada portavel, sem dependencias Python externas, para stack dev isolada."""
import argparse
import os
import re
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.dev.local"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("configure", "up", "stop", "status", "check", "test-configure", "test", "test-stop"))
    parser.add_argument("--instance", default="", help="Sufixo para uma stack independente")
    parser.add_argument("--http-port", type=int, default=8088)
    parser.add_argument("--management-port", type=int, default=15688)
    args = parser.parse_args()
    if args.instance and not re.fullmatch(r"[a-z][a-z0-9-]{0,23}", args.instance):
        parser.error("Instancia deve usar letras minusculas, numeros e hifen.")
    if not all(1024 <= p <= 65535 for p in (args.http_port, args.management_port)):
        parser.error("Portas devem estar entre 1024 e 65535.")
    suffix = "-" + args.instance if args.instance else ""
    env_suffix = "." + args.instance if args.instance else ""
    config_file = ROOT / (".env.dev" + env_suffix + ".local")
    if args.action.startswith("test"):
        test_env = ROOT / (".env.team-test" + env_suffix + ".local")
        if args.action == "test-configure":
            with test_env.open("x", encoding="utf-8") as stream:
                for name in ("TEAM_TEST_DB_PASSWORD", "TEAM_TEST_RABBIT_PASSWORD", "TEAM_TEST_JWT_SECRET"):
                    stream.write(name + "=" + secrets.token_hex(32) + "\n")
            if os.name != "nt":
                test_env.chmod(0o600)
            print("Segredos de testes novos gerados; valores omitidos.")
            return
        if not test_env.is_file():
            parser.error("Execute primeiro: python scripts/dev.py test-configure")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("TEAM_TEST_", "COMPOSE_"))}
        command = ["docker", "compose", "--project-name", "hunter-team-test" + suffix, "--env-file", str(test_env),
                   "-f", str(ROOT / "compose.team-test.yaml")]
        if args.action == "test-stop":
            subprocess.run(command + ["stop"], cwd=ROOT, env=env, check=True)
        else:
            subprocess.run(command + ["build", "runner"], cwd=ROOT, env=env, check=True)
            subprocess.run(command + ["up", "-d", "--wait", "postgres", "rabbitmq"], cwd=ROOT, env=env, check=True)
            subprocess.run(command + ["run", "--no-deps", "runner"], cwd=ROOT, env=env, check=True)
        return
    if args.action == "configure":
        # Nao substitui credenciais existentes nem depende do cofre do operador.
        with config_file.open("x", encoding="utf-8") as stream:
            for name in ("DEV_DB_PASSWORD", "DEV_RABBIT_PASSWORD", "DEV_JWT_SECRET"):
                stream.write(name + "=" + secrets.token_hex(32) + "\n")
            stream.write(f"DEV_HTTP_PORT={args.http_port}\nDEV_MANAGEMENT_PORT={args.management_port}\n")
        if os.name != "nt":
            config_file.chmod(0o600)
        print("Configuracao dev criada em arquivo ignorado; nao compartilhe esse arquivo.")
        return
    if not config_file.is_file():
        parser.error("Execute primeiro: python scripts/dev.py configure")
    # Variaveis do terminal nao podem redirecionar a stack ou reutilizar segredos.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("DEV_", "COMPOSE_"))}
    command = ["docker", "compose", "--project-name", "hunter-dev" + suffix, "--env-file", str(config_file),
               "-f", str(ROOT / "compose.dev.yaml")]
    azure_file = ROOT / ".env.azure.local"
    if azure_file.is_file():
        # Integracao Azure opcional: segredos em arquivo ignorado, worker no perfil azure.
        command[6:6] = ["--env-file", str(azure_file)]
        env["COMPOSE_PROFILES"] = "azure"
    actions = {"up": ["up", "-d", "--build", "--wait"], "stop": ["stop"],
               "status": ["ps"], "check": ["config", "--quiet"]}
    subprocess.run(command + actions[args.action], cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
