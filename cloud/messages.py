"""Contrato das mensagens da Azure Queue Storage (JSON pequeno e validado)."""
import json
import uuid
from datetime import datetime, timezone

KINDS = {"exportar_catalogo"}
MAX_BYTES = 2048


class InvalidMessage(ValueError):
    pass


def build(kind, requested_by="cli"):
    if kind not in KINDS:
        raise InvalidMessage("Tipo de mensagem desconhecido.")
    if not isinstance(requested_by, str) or not 1 <= len(requested_by) <= 64:
        raise InvalidMessage("Origem invalida.")
    return {
        "id": str(uuid.uuid4()),
        "tipo": kind,
        "origem": requested_by,
        "solicitado_em": datetime.now(timezone.utc).isoformat(),
    }


def encode(message):
    return json.dumps(message, ensure_ascii=True, separators=(",", ":"))


def parse(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
        raise InvalidMessage("Mensagem ausente ou grande demais.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise InvalidMessage("Mensagem nao e JSON.") from None
    if not isinstance(data, dict) or data.get("tipo") not in KINDS:
        raise InvalidMessage("Tipo de mensagem desconhecido.")
    try:
        uuid.UUID(str(data.get("id")))
        datetime.fromisoformat(str(data.get("solicitado_em")))
    except ValueError:
        raise InvalidMessage("Identificador ou data invalidos.") from None
    origin = data.get("origem")
    if not isinstance(origin, str) or not 1 <= len(origin) <= 64:
        raise InvalidMessage("Origem invalida.")
    return data
