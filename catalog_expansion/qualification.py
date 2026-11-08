"""Contrato conservador da campanha: dados completos e evidencias, sem HTTP/DML."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


def https(value):
    try:
        u = urlsplit(value)
        return (u.scheme == "https" and bool(u.hostname) and not u.username
                and not u.password and not u.fragment and not any(c.isspace() for c in value))
    except (TypeError, ValueError, AttributeError):
        return False


def timestamp(value):
    try:
        result = datetime.fromisoformat(value) if isinstance(value, str) else value
        return result if isinstance(result, datetime) and result.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def qualification_errors(record, *, baseline_ids, allowed_offers, campaign_started_at, now=None):
    """Valida o contrato; correspondencia semantica da imagem exige revisao real.

    Nao coleta, nao cadastra, nao libera fonte e nao substitui verificacao humana.
    allowed_offers deve vir de lista revisada, nunca de URLs inferidas de nomes.
    """
    now = now or datetime.now(timezone.utc)
    errors = []
    if not record.get("produto_id") or record["produto_id"] in baseline_ids:
        errors.append("produto_nao_e_novo")
    for field in ("nome", "marca", "modelo", "categoria", "loja"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append("campo_ausente_" + field)
    offer = record.get("link")
    image = record.get("imagem_url")
    if not https(offer) or offer not in allowed_offers:
        errors.append("oferta_sem_url_permitida")
    if not https(image):
        errors.append("imagem_sem_https_publico")
    try:
        price = Decimal(str(record.get("preco")))
        if not price.is_finite() or price <= 0 or price != price.quantize(Decimal(".01")):
            raise ValueError()
    except (InvalidOperation, ValueError):
        errors.append("preco_invalido")
    collected = timestamp(record.get("coletado_em"))
    started = timestamp(campaign_started_at)
    if not collected or not started or not started <= collected <= now:
        errors.append("coleta_sem_data_valida_da_campanha")
    history = record.get("historico", {})
    if (not history.get("observacao_id") or history.get("produto_id") != record.get("produto_id")
            or timestamp(history.get("coletado_em")) != collected):
        errors.append("historico_inicial_nao_comprovado")
    proof = record.get("evidencia_oferta", {})
    if (proof.get("url") != offer or proof.get("http_status") != 200
            or timestamp(proof.get("coletado_em")) != collected):
        errors.append("preco_e_link_nao_verificados_na_fonte")
    # A imagem deve ser uma das comprovadas para a mesma marca/modelo na fonte.
    identity = record.get("evidencia_identidade", {})
    if (identity.get("url") != offer or identity.get("marca") != record.get("marca")
            or identity.get("modelo") != record.get("modelo")
            or identity.get("categoria") != record.get("categoria")
            or image not in identity.get("imagens_do_modelo", [])
            or identity.get("revisao_confirmada") is not True):
        errors.append("identidade_ou_imagem_do_modelo_nao_confirmada")
    browser = record.get("evidencia_frontend", {})
    checked = timestamp(browser.get("verificado_em"))
    if (browser.get("produto_id") != record.get("produto_id")
            or browser.get("current_src") != image or browser.get("complete") is not True
            or not isinstance(browser.get("natural_width"), int) or browser.get("natural_width", 0) <= 0
            or not checked or not collected or not collected <= checked <= now):
        errors.append("imagem_nao_validada_no_frontend")
    for field in ("busca", "filtros", "comparacao"):
        if browser.get(field) is not True:
            errors.append("integracao_nao_validada_" + field)
    return errors


def campaign_summary(records, **context):
    seen = set()
    completed = []
    rejected = []
    for record in records:
        errors = qualification_errors(record, **context)
        identity = record.get("produto_id")
        offer = record.get("link")
        if identity in seen or offer in seen:
            errors.append("produto_duplicado_na_campanha")
        seen.update((identity, offer))
        if errors:
            rejected.append({"produto_id": identity, "motivos": errors})
        else:
            completed.append(identity)
    return {"meta": 50, "concluidos": len(completed), "faltantes": max(0, 50-len(completed)),
            "produtos_concluidos": completed, "rejeitados": rejected}
