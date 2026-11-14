"""Filas duráveis, entrega persistente, confirmação do publisher e ACK manual."""
import json
from contextlib import asynccontextmanager

import aio_pika


class Broker:
    def __init__(self, channel, work, dead):
        self.channel, self.work, self.dead = channel, work, dead

    async def publish(self, event_id, dead=False):
        message = aio_pika.Message(
            json.dumps({'version': 1, 'event_id': str(event_id)}).encode(),
            content_type='application/json', message_id=str(event_id),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
        result = await self.channel.default_exchange.publish(
            message, routing_key=(self.dead if dead else self.work).name,
            mandatory=True, timeout=10)
        if result is False:
            raise RuntimeError('Broker não confirmou a publicação')

    async def quarantine(self, body_hash):
        message = aio_pika.Message(json.dumps({'rejected_body_hash': body_hash}).encode(),
                                  delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
        result = await self.channel.default_exchange.publish(message, routing_key=self.dead.name,
                                                             mandatory=True, timeout=10)
        if result is False:
            raise RuntimeError('Broker nao confirmou a quarentena')


@asynccontextmanager
async def connect(settings, purpose='price'):
    if purpose not in ('price', 'analytics', 'nlp'):
        raise ValueError('Fila desconhecida')
    connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=10)
    try:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        await channel.set_qos(prefetch_count=10)
        dead = await channel.declare_queue(settings.prefix + '.' + purpose + '.dead', durable=True,
                                           arguments={'x-queue-type': 'quorum'})
        work = await channel.declare_queue(settings.prefix + '.' + purpose, durable=True,
            arguments={'x-queue-type': 'quorum', 'x-dead-letter-exchange': '',
                       'x-dead-letter-routing-key': dead.name})
        yield Broker(channel, work, dead)
    finally:
        await connection.close()
