"""Validacao central; erros nunca incluem valores de conexao ou credenciais."""

import os
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, unquote, urlsplit


def required(name):
    value = os.environ.get(name, "")
    if not value.strip():
        raise ValueError(f"Configure {name} no ambiente.")
    return value


def bounded_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, default))
        if minimum <= value <= maximum:
            return value
    except (TypeError, ValueError):
        pass
    raise ValueError(f"Configuracao invalida: {name}.")


def environment():
    value = os.environ.get("HUNTER_ENV", "local")
    if value not in ("local", "test", "production"):
        raise ValueError("HUNTER_ENV deve ser local, test ou production.")
    return value


def validate_url(value, schemes, name):
    try:
        parts = urlsplit(value)
        if (
            parts.scheme not in schemes
            or not parts.hostname
            or parts.fragment
            or any(c.isspace() for c in value)
        ):
            raise ValueError()
        _ = parts.port
        # Parametros de conexao nao podem substituir identidade/host da URL.
        query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        if any(
            k not in ("sslmode", "sslrootcert", "sslcert", "sslkey", "application_name")
            for k, _ in query
        ):
            raise ValueError()
        if len({k for k, _ in query}) != len(query):
            raise ValueError()
        return parts
    except (ValueError, TypeError, AttributeError):
        raise ValueError(
            f"URL invalida: {name}; confira formato e parametros."
        ) from None


def require_test_database(value):
    parts = validate_url(value, ("postgresql", "postgres"), "banco isolado")
    if (
        os.environ.get("HUNTER_QUEUE_TESTS") != "1"
        or parts.hostname not in ("localhost", "127.0.0.1")
        or parts.port != 55432
        or parts.path != "/hunter_test"
        or unquote(parts.username or "") != "hunter_test"
        or parts.query
    ):
        raise ValueError(
            "Testes exigem hunter_test:55432 local, usuario hunter_test e opt-in explicito."
        )
    return value


def test_database_url():
    value = required("HUNTER_TEST_DATABASE_URL")
    require_test_database(value)
    # Detecta terminal misturado antes de qualquer conexao, mesmo que o teste
    # utilize apenas HUNTER_TEST_DATABASE_URL.
    if os.environ.get("DATABASE_URL"):
        require_test_database(os.environ["DATABASE_URL"])
    if os.environ.get("MIGRATION_DATABASE_URL"):
        require_test_database(os.environ["MIGRATION_DATABASE_URL"])
    return value


def database_url(*, migration=False):
    name = "MIGRATION_DATABASE_URL" if migration else "DATABASE_URL"
    value = required(name)
    parts = validate_url(value, ("postgresql", "postgres"), name)
    if not parts.path or parts.path == "/":
        raise ValueError(f"Informe o banco em {name}.")
    if os.environ.get("HUNTER_QUEUE_TESTS") == "1" or environment() == "test":
        require_test_database(value)
    if environment() == "production":
        if not migration and unquote(parts.username or "") in ("", "postgres"):
            raise ValueError("Producao exige funcao de aplicacao dedicada.")
        if dict(parse_qsl(parts.query)).get("sslmode") != "verify-full":
            raise ValueError("Producao exige TLS verify-full na conexao PostgreSQL.")
        if migration and os.environ.get("DATABASE_URL"):
            runtime = validate_url(
                os.environ["DATABASE_URL"], ("postgresql", "postgres"), "DATABASE_URL"
            )
            if unquote(runtime.username or "") == unquote(parts.username or ""):
                raise ValueError("Funcoes de aplicacao e migracao devem ser distintas.")
    return value


def rabbitmq_url():
    value = required("RABBITMQ_URL")
    parts = validate_url(value, ("amqp", "amqps"), "RABBITMQ_URL")
    if environment() == "production" and parts.scheme != "amqps":
        raise ValueError("Producao exige AMQPS.")
    return value


def jwt_secret():
    value = required("JWT_SECRET_KEY")
    if environment() == "production" and (
        len(value) < 32
        or len(set(value)) < 8
        or value.upper().startswith(("REPLACE_", "CHANGE_", "YOUR_", "EXAMPLE"))
    ):
        raise ValueError(
            "JWT_SECRET_KEY de producao exige pelo menos 32 caracteres aleatorios."
        )
    return value


def cors_origins():
    default = (
        ""
        if environment() == "production"
        else "http://127.0.0.1:5500,http://localhost:5500"
    )
    values = tuple(
        v.strip()
        for v in os.environ.get("CORS_ORIGINS", default).split(",")
        if v.strip()
    )
    for value in values:
        parts = urlsplit(value)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.path
            or parts.query
            or parts.fragment
            or (environment() == "production" and parts.scheme != "https")
        ):
            raise ValueError(
                "CORS_ORIGINS exige origens explicitas, sem caminhos ou credenciais."
            )
    if environment() == "production" and not values:
        raise ValueError("Configure CORS_ORIGINS explicitamente em producao.")
    return values


@dataclass(frozen=True)
class APISettings:
    database_url: str = field(repr=False)
    pool_min: int = 1
    pool_max: int = 10
    command_timeout: int = 30

    @classmethod
    def load(cls):
        jwt_secret()
        low = bounded_int("DB_POOL_MIN", 1, 1, 100)
        high = bounded_int("DB_POOL_MAX", 10, 1, 100)
        if low > high:
            raise ValueError("DB_POOL_MIN nao pode exceder DB_POOL_MAX.")
        return cls(
            database_url(), low, high, bounded_int("DB_COMMAND_TIMEOUT", 30, 1, 600)
        )


def queue_prefix():
    value = os.environ.get("HUNTER_QUEUE_PREFIX", "hunter")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", value):
        raise ValueError("Prefixo de fila invalido.")
    return value


async def assert_runtime_role(conn):
    """Producao recusa privilegios administrativos; nunca altera a funcao."""
    if environment() != "production":
        return
    row = await conn.fetchrow(
        "SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user"
    )
    if row is None or any(
        row[key] for key in ("rolsuper", "rolcreatedb", "rolcreaterole")
    ):
        raise ValueError(
            "Runtime de producao exige funcao sem privilegios administrativos."
        )
