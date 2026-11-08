"""Estatistica por oferta; sem previsoes nem preenchimento de historico ausente."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

FEATURES = ['log_preco_medio', 'volatilidade_percentual', 'variacao_percentual', 'observacoes']


def prepare(rows, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    frame = pd.DataFrame([dict(row) for row in rows])
    if frame.empty:
        return frame
    frame['preco'] = pd.to_numeric(frame['preco'], errors='coerce')
    frame['coletado_em'] = pd.to_datetime(frame['coletado_em'], utc=True, errors='coerce')
    frame = frame.loc[np.isfinite(frame['preco']) & (frame['preco'] > 0)
                      & frame['coletado_em'].notna() & (frame['coletado_em'] <= now)].copy()
    # Fontes repetidas no mesmo instante nao aumentam artificialmente a amostra.
    return frame.sort_values(['coletado_em', 'id']).drop_duplicates(['produto_id', 'coletado_em'], keep='last')


def statistics(rows, now=None, threshold=5):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    frame = prepare(rows, now)
    products = []
    if not frame.empty:
        for pid, group in frame.groupby('produto_id', sort=True):
            prices = group['preco'].astype(float)
            last = group.iloc[-1]
            n = len(group)
            variation = float((prices.iloc[-1] / prices.iloc[0] - 1) * 100) if n >= 2 else None
            drop = float((1 - prices.iloc[-1] / prices.iloc[-2]) * 100) if n >= 2 else None
            discount = float((1 - prices.iloc[-1] / prices.iloc[:-1].mean()) * 100) if n >= 2 else None
            fresh = (now - last['coletado_em']).total_seconds() <= 7 * 86400
            near = n >= 2 and (last['coletado_em']-group.iloc[-2]['coletado_em']).total_seconds() <= 7*86400
            days = int(group['coletado_em'].dt.normalize().nunique())
            detected = bool(n >= 2 and fresh and near and last['disponivel'] and drop >= threshold)
            opportunity = bool(detected and n >= 3 and days >= 2 and discount >= threshold)
            products.append(dict(produto_id=int(pid), nome=str(last['nome']), loja=str(last['loja']),
                preco_atual=float(prices.iloc[-1]), preco_medio=float(prices.mean()),
                preco_minimo=float(prices.min()), preco_maximo=float(prices.max()), observacoes=n,
                dias_observados=days, variacao_percentual=variation, queda_recente_percentual=drop,
                desconto_media_anterior_percentual=discount,
                volatilidade_percentual=float(prices.std(ddof=0)/prices.mean()*100) if n >= 2 else None,
                disponivel=bool(last['disponivel']), atualizado=bool(fresh),
                primeira_observacao=group.iloc[0]['coletado_em'].isoformat(),
                ultima_observacao=last['coletado_em'].isoformat(),
                queda_detectada=detected, oportunidade=opportunity))
    return dict(produtos=products, resumo=dict(produtos=len(products), observacoes=int(len(frame)),
        quedas=sum(p['queda_detectada'] for p in products), oportunidades=sum(p['oportunidade'] for p in products)),
        limiar_percentual=threshold, mensagem=('Sem observações válidas no período.' if not products else
        'Uma observação não permite calcular variação. Oportunidades são sinais exploratórios, não garantia de compra.'))


def analytical_history(rows, now=None):
    frame = prepare(rows, now)
    if frame.empty:
        return []
    prices = frame['preco'].astype(float)
    means = prices.rolling(window=3, min_periods=3).mean()
    changes = prices.pct_change(fill_method=None) * 100
    return [dict(coletado_em=row['coletado_em'].isoformat(), preco=float(row['preco']),
        media_movel_3=None if pd.isna(means.loc[index]) else float(means.loc[index]),
        variacao_anterior_percentual=None if pd.isna(changes.loc[index]) else float(changes.loc[index]),
        disponivel=bool(row['disponivel'])) for index, row in frame.iterrows()]


def cluster_products(rows, k=3, now=None):
    if not 2 <= k <= 5:
        raise ValueError('K deve estar entre 2 e 5')
    products = statistics(rows, now)['produtos']
    eligible = [p for p in products if p['observacoes'] >= 3 and p['dias_observados'] >= 2
                and p['disponivel'] and p['atualizado']]
    minimum = max(6, 2*k)
    base = dict(k=k, produtos_elegiveis=len(eligible), minimo_produtos=minimum, features=FEATURES)
    reason = f'K-Means requer pelo menos {minimum} produtos disponíveis e recentes, cada um com 3 observações em 2 dias distintos.'
    if len(eligible) < minimum:
        return dict(base, status='dados_insuficientes', mensagem=reason, grupos=[], produtos=[])
    data = pd.DataFrame(eligible)
    data['log_preco_medio'] = np.log1p(data['preco_medio'])
    features = data[FEATURES].to_numpy(dtype=float)
    if len(np.unique(features, axis=0)) < k+1 or np.count_nonzero(np.std(features, axis=0) > 1e-10) < 2:
        return dict(base, status='dados_insuficientes', mensagem='Diversidade numérica insuficiente: são necessários k+1 vetores distintos e duas características variáveis.', grupos=[], produtos=[])
    # Import tardio: a API legada e estatisticas nao dependem do carregamento do modelo.
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    from threadpoolctl import threadpool_limits
    scaled = StandardScaler().fit_transform(features)
    with threadpool_limits(limits=1):
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(scaled)
    # Numeros dos grupos estaveis por media; nao representam qualidade ou recomendacao.
    order = sorted(set(labels), key=lambda label: float(data.loc[labels == label, 'preco_medio'].mean()))
    mapping = {label:i+1 for i,label in enumerate(order)}
    assignments = [dict(p, grupo=mapping[label]) for p,label in zip(eligible,labels)]
    groups = []
    for label in order:
        members = [p for p in assignments if p['grupo'] == mapping[label]]
        groups.append(dict(grupo=mapping[label], produtos=len(members),
            preco_medio=float(np.mean([p['preco_medio'] for p in members])),
            variacao_media_percentual=float(np.mean([p['variacao_percentual'] for p in members]))))
    return dict(base, status='ok', mensagem='Agrupamento exploratório; grupos não identificam produtos equivalentes nem preveem preços.', grupos=groups, produtos=assignments)
