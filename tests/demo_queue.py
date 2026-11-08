"""Demonstração automatizada: dois workers reais, duplicatas e falha até a DLQ."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from messaging.config import Settings
from messaging.testing import require_isolated


async def state(settings, user):
    require_isolated(settings)
    conn = await asyncpg.connect(settings.database_url)
    try:
        events = await conn.fetch('SELECT status,attempts,payload FROM hunter_events WHERE usuario_id=$1', user)
        notices = await conn.fetchval('SELECT count(*) FROM hunter_notifications WHERE usuario_id=$1', user)
        return [dict(row) for row in events], notices
    finally:
        await conn.close()


def main():
    settings = Settings.environment()
    require_isolated(settings)
    root = Path(__file__).resolve().parents[1]
    def demo(action):
        subprocess.run([sys.executable,'-B','-m','messaging.demo',action], cwd=root, check=True)
    demo('seed')
    demo('failure')
    user = json.loads((root / '.hunter-demo.local.json').read_text(encoding='utf-8'))['usuario_id']
    env = os.environ.copy()
    env['HUNTER_SCAN_SECONDS'] = '1'
    env['HUNTER_RETRY_SECONDS'] = '1'
    workers, logs = [], []
    try:
        for module, args in [('messaging.worker',['--demo-failures']), ('messaging.worker',['--demo-failures']), ('messaging.scheduler',[])]:
            log = tempfile.TemporaryFile(mode='w+b')
            logs.append(log)
            workers.append(subprocess.Popen([sys.executable,'-B','-m',module]+args, cwd=root, env=env,
                stdout=log, stderr=log, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)))
        for _ in range(100):
            events, notices = asyncio.run(state(settings, user))
            if events and all(e['status'] in ('processed','dead') for e in events) and any(e['status']=='dead' and e['attempts']==3 for e in events) and notices == 1:
                break
            time.sleep(.2)
        else:
            raise AssertionError('Demonstração não concluiu processamento/DLQ')
        demo('duplicate')
        time.sleep(2)
        _, notices = asyncio.run(state(settings, user))
        assert notices == 1, 'Notificação duplicada'
        demo('status')
        print('OK: dois workers reais, ACK, falha simulada em 3 tentativas, DLQ confirmada e duplicatas sem novo aviso.')
    finally:
        for process in workers:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
