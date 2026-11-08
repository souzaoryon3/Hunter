"""Lock vitalicio e heartbeat do unico scheduler por banco."""
import os
from time import time as wall_time, monotonic as monotonic_time
from uuid import uuid4

LOCK=281236


class SchedulerGuard:
    def __init__(self,conn):
        self.conn=conn
        self.instance=uuid4()
        self.previous_wall=None
        self.previous_monotonic=None
        self.enabled=False

    async def start(self):
        if not await self.conn.fetchval('SELECT pg_try_advisory_lock($1::bigint)',LOCK):
            return False
        self.enabled=bool(await self.conn.fetchval("SELECT to_regclass('hunter_scheduler_heartbeat') IS NOT NULL"))
        if self.enabled:
            await self.conn.execute('''INSERT INTO hunter_scheduler_heartbeat
                (instance_id,process_id,started_at,last_seen_at,state)
                VALUES($1,$2,clock_timestamp(),clock_timestamp(),'running')
                ON CONFLICT(singleton) DO UPDATE SET instance_id=EXCLUDED.instance_id,
                process_id=EXCLUDED.process_id,started_at=EXCLUDED.started_at,
                last_gap_seconds=GREATEST(0,extract(epoch FROM clock_timestamp()-hunter_scheduler_heartbeat.last_seen_at)),
                max_gap_seconds=GREATEST(hunter_scheduler_heartbeat.max_gap_seconds,
                    extract(epoch FROM clock_timestamp()-hunter_scheduler_heartbeat.last_seen_at)),
                last_seen_at=EXCLUDED.last_seen_at,state='running' ''',self.instance,os.getpid())
        return True

    async def tick(self):
        wall=wall_time();mono=monotonic_time()
        gap=max(0,wall-self.previous_wall) if self.previous_wall is not None else 0
        drift=(wall-self.previous_wall)-(mono-self.previous_monotonic) if self.previous_wall is not None else 0
        self.previous_wall=wall;self.previous_monotonic=mono
        # Mesmo sem 005, a conexao do lock precisa estar viva antes de scan.
        await self.conn.fetchval('SELECT 1')
        if self.enabled:
            await self.conn.execute('''UPDATE hunter_scheduler_heartbeat SET last_seen_at=clock_timestamp(),
                last_gap_seconds=$2,max_gap_seconds=GREATEST(max_gap_seconds,$2),clock_drift_seconds=$3
                WHERE instance_id=$1''',self.instance,gap,drift)

    async def stop(self):
        if self.enabled and not self.conn.is_closed():
            await self.conn.execute("UPDATE hunter_scheduler_heartbeat SET state='stopped' WHERE instance_id=$1",self.instance)
