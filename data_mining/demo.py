"""Dados explicitamente sinteticos; gerados em memoria, nunca gravados no catalogo."""
from datetime import datetime, timedelta, timezone


def demo_rows(now=None):
    anchor = (now or datetime.now(timezone.utc)).replace(hour=0, minute=0, second=0, microsecond=0)
    patterns = ([1,1.01,1,.99,1.02,1.01,1,.99],
                [1,.98,.96,.94,.92,.90,.88,.77],
                [1,.85,1.2,.9,1.25,1,.8,.7])
    rows=[]
    for pid in range(1,10):
        group=(pid-1)//3
        base=(80,320,1100)[group]+(pid%3)*13
        for day,factor in enumerate(patterns[group]):
            rows.append(dict(id=pid*100+day, produto_id=pid,
                nome=f'Produto demonstrativo {pid:02d}', loja='Loja fictícia',
                preco=round(base*factor,2), coletado_em=anchor-timedelta(days=7-day),
                disponivel=True, fonte_coleta='sintetico_demo'))
    return rows
