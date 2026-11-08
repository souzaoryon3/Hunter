"""Operacoes explicitas: inspecao, backup verificavel, migracao e vinculo existentes.

Destino principal fixado e verificado. Nao executa coleta nem inicia servicos.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime
from urllib.parse import urlsplit,unquote

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main_dsn():
    from config.settings import database_url
    dsn=database_url()
    url=urlsplit(dsn)
    if url.hostname not in ('localhost','127.0.0.1','::1') or (url.port or 5432)!=5432 or url.path!='/hunter_db':
        raise ValueError('Destino principal hunter_db:5432 nao confirmado')
    return dsn


def main_admin_dsn(runtime_dsn):
    from config.settings import database_url
    admin=database_url(migration=True)
    runtime,target=urlsplit(runtime_dsn),urlsplit(admin)
    loopback={'localhost','127.0.0.1','::1'}
    same_host=(runtime.hostname==target.hostname or {runtime.hostname,target.hostname}<=loopback)
    if not same_host or (runtime.port or 5432)!=(target.port or 5432) or runtime.path!=target.path:
        raise ValueError('Destino administrativo difere do runtime; backup/migracao recusados.')
    return admin


async def inspect(conn):
    versions={r['version']:r['checksum'] for r in await conn.fetch('SELECT version,checksum FROM hunter_schema_migrations')}
    filenames={'002':'002_alertas_assincronos.sql','003':'003_catalogo_historico.sql',
               '004':'004_catalogo_candidatos.sql','005':'005_rotacao_multiloja.sql'}
    for version,checksum in versions.items():
        if version in filenames and hashlib.sha256((ROOT/'migrations'/filenames[version]).read_text(encoding='utf-8').encode()).hexdigest()!=checksum:
            raise ValueError('Checksum divergente')
    print('Destino: hunter_db, localhost:5432; migracoes='+','.join(sorted(versions)))
    print(json.dumps(dict(await conn.fetchrow('''SELECT
        (SELECT count(*) FROM hunter_catalog_products) products,
        (SELECT count(*) FROM hunter_price_observations) observations,
        (SELECT count(DISTINCT produto_id) FROM hunter_price_observations WHERE imagem_url IS NOT NULL) images'''))))
    for name in ('hunter_catalog_sources','hunter_catalog_candidates','hunter_catalog_runs'):
        print(name, bool(await conn.fetchval('SELECT to_regclass($1)',name)))
    return versions


async def fingerprint(conn):
    # Somente campos preexistentes: adicionar metadados nao muda o fingerprint.
    result=[]
    for sql in ("SELECT id,loja,link,created_at FROM hunter_catalog_products ORDER BY id",
                "SELECT id,produto_id,nome,imagem_url,preco,coletado_em,fonte_coleta,fonte_url FROM hunter_price_observations ORDER BY id"):
        rows=[dict(r) for r in await conn.fetch(sql)]
        result.append(hashlib.sha256(json.dumps(rows,default=str,sort_keys=True).encode()).hexdigest())
    return result


def backup(dsn):
    folder=Path(os.environ['TEMP'])/'HunterBackups'
    folder.mkdir(exist_ok=True)
    path=folder/('hunter_pre_stage2_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.dump')
    binpath=Path(r'C:\Program Files\PostgreSQL\16\bin')
    u=urlsplit(dsn);env=os.environ.copy();env['PGPASSWORD']=unquote(u.password or '')
    args=[str(binpath/'pg_dump.exe'),'-h',u.hostname,'-p',str(u.port or 5432),'-U',unquote(u.username or ''),'-d','hunter_db','-Fc','-f',str(path)]
    result=subprocess.run(args,env=env,capture_output=True)
    if result.returncode:
        raise ValueError('pg_dump falhou; mensagem omitida para proteger segredos')
    result=subprocess.run([str(binpath/'pg_restore.exe'),'--list',str(path)],capture_output=True)
    if result.returncode or path.stat().st_size==0:
        raise ValueError('Backup invalido')
    print('Backup verificado:',path,'bytes=',path.stat().st_size,'sha256=',hashlib.sha256(path.read_bytes()).hexdigest())
    return path


async def run(args):
    import asyncpg
    dsn=main_dsn()
    conn=await asyncpg.connect(dsn,server_settings={'default_transaction_read_only':'on'})
    try:
        if await conn.fetchval('SELECT current_database()')!='hunter_db':
            raise ValueError('Banco nao confirmado')
        versions=await inspect(conn)
        if not {'002','003'} <= versions.keys():
            raise ValueError('Migracoes base ausentes')
        before=await fingerprint(conn)
        for version,table in (('004','hunter_catalog_sources'),('004','hunter_catalog_candidates'),
                              ('004','hunter_catalog_runs'),('005','hunter_catalog_shops'),
                              ('005','hunter_collection_control'),('005','hunter_scheduler_heartbeat')):
            if version not in versions and await conn.fetchval('SELECT to_regclass($1)',table):
                raise ValueError('Colisao estrutural: revisar antes de migrar')
    finally:
        await conn.close()
    if args.action=='inspect':
        return
    if args.action=='migrate':
        backup(main_admin_dsn(dsn)) # Backup usa funcao administrativa; nunca concede privilegios ao runtime.
        from messaging.migrate import migrate
        await migrate('004')
        await migrate('005')
        conn=await asyncpg.connect(dsn,server_settings={'default_transaction_read_only':'on'})
        try:
            if before!=await fingerprint(conn):
                raise ValueError('Conteudo do catalogo mudou; conferir antes de continuar')
            print('Fingerprint dos produtos e historico preservado.')
        finally:
            await conn.close()
    elif args.action=='seed':
        from scraping.periodic import CollectionSettings,Journal,state_path
        from catalog_expansion.rotation import seed_existing
        conn=await asyncpg.connect(dsn)
        try:
            if not await conn.fetchval("SELECT to_regclass('hunter_collection_control')"):
                raise ValueError('Migracoes pendentes')
            print('Candidatos existentes associados:',await seed_existing(conn,CollectionSettings.environment(),Journal(state_path(dsn))))
        finally:
            await conn.close()
    elif args.action=='restart':
        conn=await asyncpg.connect(dsn)
        try:
            # O coletor antigo tambem usa este lock: nao interromper HTTP ativo.
            if not await conn.fetchval('SELECT pg_try_advisory_lock(281235)'):
                raise ValueError('Coleta em andamento; reinicio adiado')
            if not await conn.fetchval("SELECT EXISTS(SELECT 1 FROM hunter_schema_migrations WHERE version='005')"):
                raise ValueError('005 ausente')
            env=os.environ.copy();env['DATABASE_URL']=dsn;env['HUNTER_CATALOG_HANDOFF']='1'
            command=['powershell.exe','-NoProfile','-File',str(ROOT/'scripts/restart_catalog.ps1')]
            if args.scheduler_only:
                command.append('-SchedulerOnly')
            if args.api_only:
                command.append('-ApiOnly')
            process=await asyncio.create_subprocess_exec(*command,env=env)
            if await process.wait():
                raise ValueError('Handoff nao concluido; conferir processos')
        finally:
            await conn.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('inspect','migrate','seed','restart'))
    parser.add_argument('--scheduler-only',action='store_true')
    parser.add_argument('--api-only',action='store_true')
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception as exc:
        print('Operacao interrompida:',type(exc).__name__,'(sem detalhes sensiveis)')
        sys.exit(1)
