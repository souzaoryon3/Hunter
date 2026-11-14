-- TEMPLATE MANUAL: NAO e migracao e NAO e executado pela aplicacao/testes.
-- Revisar com o operador. Executar somente apos autorizacao separada.
-- Nao inclui senhas. Criar logins/definir senhas via canal administrativo seguro.
-- Grupo owner recebe DDL; runtime recebe somente DML necessario.
BEGIN;
DO $$ BEGIN
    IF current_database() <> 'hunter_db' THEN
        RAISE EXCEPTION 'Confirme o banco principal antes de preparar funcoes';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='hunter_owner') THEN
        CREATE ROLE hunter_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
    IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='hunter_runtime') THEN
        CREATE ROLE hunter_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END $$;
GRANT USAGE ON SCHEMA public TO hunter_runtime;
GRANT USAGE, CREATE ON SCHEMA public TO hunter_owner;
GRANT CONNECT ON DATABASE hunter_db TO hunter_runtime, hunter_owner;
GRANT SELECT,INSERT,UPDATE,DELETE ON usuarios,alertas_preco,feedbacks TO hunter_runtime;
GRANT SELECT ON produtos_kabum,produtos_mercadolivre,produtos_pichau,hunter_schema_migrations TO hunter_runtime;
GRANT SELECT,INSERT,UPDATE ON hunter_alert_state,hunter_events,hunter_notifications,
    hunter_message_rejections,hunter_catalog_sources,hunter_catalog_candidates,
    hunter_catalog_runs,hunter_catalog_products,hunter_catalog_shops,
    hunter_collection_control,hunter_scheduler_heartbeat TO hunter_runtime;
GRANT SELECT,INSERT ON hunter_processing_log,hunter_price_observations TO hunter_runtime;
-- Apos aplicar 007; o trigger de observacoes usa os privilegios do runtime.
GRANT SELECT,INSERT,UPDATE ON hunter_analytics_events TO hunter_runtime;
GRANT SELECT,INSERT ON hunter_analytics_results TO hunter_runtime;
-- Apos aplicar 009; nenhuma permissao sobre textos privados e necessaria.
GRANT SELECT,INSERT,UPDATE ON hunter_nlp_events TO hunter_runtime;
GRANT SELECT,INSERT ON hunter_text_results TO hunter_runtime;
-- Gatilhos de usuarios atuais sao SECURITY INVOKER e gravam nesta auditoria.
GRANT INSERT ON auditoria_usuarios TO hunter_runtime;
DO $$ DECLARE item record; sequence_name text; BEGIN
    FOR item IN SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND (table_name IN ('usuarios','alertas_preco','feedbacks','auditoria_usuarios')
            OR table_name LIKE 'hunter\_%' ESCAPE '\') LOOP
        IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public'
            AND table_name=item.table_name AND column_name='id') THEN
            sequence_name:=pg_get_serial_sequence(format('public.%I',item.table_name),'id');
            IF sequence_name IS NOT NULL THEN
                EXECUTE format('GRANT USAGE,SELECT ON SEQUENCE %s TO hunter_runtime',sequence_name);
            END IF;
        END IF;
    END LOOP;
END $$;
COMMIT;
-- PENDENTE DE REVISAO: propriedade das tabelas/sequencias/funcoes existentes e
-- default privileges do owner para novas migracoes. Nao executar REASSIGN OWNED
-- indiscriminadamente. Nenhum login e criado/alterado por este template.
-- Associar futuramente hunter_app -> hunter_runtime; hunter_migration -> owner.
-- Revisar gatilhos de auditoria, ACL publica e grant futuro antes de trocar DSN.
