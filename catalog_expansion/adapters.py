"""Registro extensivel. Cadastrar fonte nao instala nem autoriza um adaptador."""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from scraping.public_sources import collect_sample


@dataclass
class FetchResult:
    items: list
    status: str
    http_status: int | None = None
    retry_after: datetime | None = None


def retry_after(value, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        from datetime import timedelta
        if str(value).strip().isdigit():
            return now+timedelta(seconds=int(value))
        stamp=parsedate_to_datetime(value)
        return max(now,stamp.astimezone(timezone.utc)) if stamp.tzinfo else None
    except (ValueError,TypeError,OverflowError):
        return None


def public_product(source,candidate):
    import re
    from urllib.parse import urlsplit
    target=urlsplit(candidate['canonical_url'])
    if (source['loja']!='KaBuM!' or source['integration_type']!='public_page'
            or target.netloc!='www.kabum.com.br' or target.query
            or not re.match(r'^/produto/\d+/',target.path)):
        raise ValueError('Adaptador restrito a paginas pontuais KaBuM autorizadas')
    items,status,meta=collect_sample(source['loja'],1,candidate['canonical_url'],with_metadata=True,
        request_delay=source['request_delay_seconds'])
    return FetchResult(items,status,meta.get('http_status'),retry_after(meta.get('retry_after')))


# Unica via ativavel nesta entrega: as paginas pontuais KaBuM ja monitoradas.
# Novas APIs/feeds precisam de implementacao revisada e permission_reference.
ADAPTERS={'kabum_public':public_product}
