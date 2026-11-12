"""Aplica somente a migração incremental da fila, explicitamente e em transação."""
import asyncio
import argparse
import hashlib
import os
from pathlib import Path

import asyncpg
from config.settings import database_url


async def migrate(version='002'):
    if version not in ('002', '003', '004', '005', '006'):
        raise ValueError('Versao desconhecida')
    dsn = database_url(migration=True)
    filename = {'002': '002_alertas_assincronos.sql', '003': '003_catalogo_historico.sql',
                '004': '004_catalogo_candidatos.sql', '005': '005_rotacao_multiloja.sql',
                '006': '006_lojas_tecnologia.sql'}[version]
    sql = (Path(__file__).resolve().parents[1] / 'migrations' / filename).read_text(encoding='utf-8')
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL lock_timeout='5s'")
            await conn.execute('SELECT pg_advisory_xact_lock(281234)')
            for table in ('usuarios', 'alertas_preco', 'produtos_kabum', 'produtos_mercadolivre', 'produtos_pichau'):
                if not await conn.fetchval('SELECT to_regclass($1)', table):
                    raise ValueError('Esquema base incompleto; confira as migrações anteriores.')
            await conn.execute('''CREATE TABLE IF NOT EXISTS hunter_schema_migrations (
                version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
            old = await conn.fetchval('SELECT checksum FROM hunter_schema_migrations WHERE version=$1', version)
            if version == '005' and not await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM hunter_schema_migrations WHERE version='004')"):
                raise ValueError('A migracao 005 exige a 004 aplicada.')
            if version == '006' and not await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM hunter_schema_migrations WHERE version='005')"):
                raise ValueError('A migracao 006 exige a 005 aplicada.')
            if version == '004' and (not await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM hunter_schema_migrations WHERE version='003')")
                    or not await conn.fetchval("SELECT to_regclass('hunter_catalog_products')")):
                raise ValueError('A migracao 004 exige a 003 aplicada.')
            if old and old != checksum:
                raise ValueError('Migração já aplicada com conteúdo diferente; crie outra migração.')
            if not old:
                await conn.execute(sql)
                await conn.execute('INSERT INTO hunter_schema_migrations(version,checksum) VALUES ($1,$2)', version, checksum)
        print(f'Migração {version} conferida/aplicada sem remover dados.')
    finally:
        await conn.close()


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--version', choices=('002', '003', '004', '005', '006'), default='002')
        asyncio.run(migrate(parser.parse_args().version))
    except Exception as exc:
        print('Migração não concluída: ' + type(exc).__name__ + '. Confira a configuração e o esquema base.')
        raise SystemExit(1) from None
