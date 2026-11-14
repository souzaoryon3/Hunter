"""PLN continuo pelo RabbitMQ; reutiliza entrega confiavel do pipeline analitico."""
import asyncio

from data_mining.streaming import run
from messaging.runtime import configure_logging
from nlp.analysis import analyze


async def process_event(conn, identity):
    async with conn.transaction():
        event = await conn.fetchrow('''SELECT * FROM hunter_nlp_events
            WHERE observation_id=$1 FOR UPDATE''', identity)
        if not event:
            return 'unknown'
        if event['status'] in ('processed','dead_pending','dead'):
            return 'duplicate'
        if event['failures'] and event['available_at'] > await conn.fetchval('SELECT now()'):
            return 'deferred'
        observation = await conn.fetchrow('''SELECT nome,produto_id,coletado_em
            FROM hunter_price_observations WHERE id=$1''', identity)
        if observation['coletado_em'] > await conn.fetchval('SELECT now()'):
            raise ValueError('Observacao futura')
        result = analyze(observation['nome'])
        await conn.execute('''INSERT INTO hunter_text_results(observation_id,produto_id,event_time,
            replay,normalized_text,tokens,keywords,category,matched_categories,algorithm)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)''', identity, observation['produto_id'],
            observation['coletado_em'], event['replay'], result['normalized_text'], result['tokens'],
            result['keywords'], result['category'], result['matched_categories'], result['algorithm'])
        await conn.execute('''UPDATE hunter_nlp_events SET status='processed',
            processed_at=clock_timestamp(),error_code=NULL WHERE observation_id=$1''', identity)
    return 'processed'


if __name__ == '__main__':
    configure_logging()
    try:
        asyncio.run(run(purpose='nlp', event_table='hunter_nlp_events', processor=process_event))
    except KeyboardInterrupt:
        pass
