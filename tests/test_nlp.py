"""PLN deterministico de titulos publicos, sem modelos ou dados pessoais."""
import os
import secrets
import unittest
from datetime import datetime, timedelta, timezone

import asyncpg

from nlp.analysis import analyze, query_tokens
from nlp.streaming import process_event
from messaging.config import Settings
from messaging.testing import require_isolated


class TextAnalysisTests(unittest.TestCase):
    def test_portuguese_normalization_and_stopwords(self):
        result = analyze('  TECLADO Mecânico para o Computador!  ')
        self.assertEqual(result['tokens'], ['teclado', 'mecanico', 'computador'])
        self.assertEqual(result['normalized_text'], 'teclado mecanico computador')
        self.assertEqual(result['category'], 'teclado')

    def test_html_is_text_and_scripts_are_excluded(self):
        result = analyze('<b>Mouse</b> &amp; USB <script>alert(1)</script>')
        self.assertEqual(result['tokens'], ['mouse', 'usb'])
        self.assertEqual(result['category'], 'mouse')

    def test_multi_category_and_unknown_are_explicit(self):
        result = analyze('Kit teclado e mouse')
        self.assertEqual(result['category'], 'multicategoria')
        self.assertEqual(set(result['matched_categories']), {'teclado','mouse'})
        self.assertEqual(analyze('Produto XPTO 123')['category'], 'outros')

    def test_combo_preserves_separate_mouse_and_mousepad(self):
        # Regressao: o acessorio mousepad nao pode apagar o mouse do mesmo kit.
        for title in ('Kit teclado, mouse e mousepad', 'Mouse pad e mouse gamer'):
            with self.subTest(title=title):
                result = analyze(title)
                self.assertEqual(result['category'], 'multicategoria')
                self.assertIn('mouse', result['matched_categories'])
                self.assertIn('mousepad', result['matched_categories'])

    def test_mousepad_and_models(self):
        self.assertEqual(analyze('Mouse pad gamer')['category'], 'mousepad')
        self.assertEqual(analyze('Mousepad XL')['category'], 'mousepad')
        self.assertIn('g502', analyze('Mouse Logitech G502')['tokens'])
        self.assertIn('usb-c', analyze('Cabo USB-C')['tokens'])

    def test_synonyms_and_plural(self):
        self.assertEqual(analyze('Teclados gamer')['category'], 'teclado')
        self.assertEqual(analyze('Fone de ouvido')['category'], 'headset')
        self.assertEqual(analyze('Solid State SSD M.2')['category'], 'armazenamento')

    def test_keywords_frequency_and_input_limits(self):
        self.assertEqual(analyze('mouse gamer mouse')['keywords'][0], 'mouse')
        self.assertEqual(query_tokens('  MECÂN  '), ['mecan'])
        self.assertEqual(query_tokens('de e para'), [])
        for text in ('', '   ', 'x'*501):
            with self.assertRaises(ValueError):
                analyze(text)


@unittest.skipUnless(os.environ.get('HUNTER_QUEUE_TESTS') == '1', 'Exige banco isolado')
class TextIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        settings = Settings.environment()
        require_isolated(settings)
        self.conn = await asyncpg.connect(settings.database_url)
        self.addAsyncCleanup(self.conn.close)
        self.tx = self.conn.transaction()
        await self.tx.start()
        self.addAsyncCleanup(self.tx.rollback)
        self.marker = 'nlp'+secrets.token_hex(6)
        self.pid = await self.conn.fetchval('''INSERT INTO hunter_catalog_products(loja,link)
            VALUES('KaBuM!',$1) RETURNING id''', 'https://example.com/'+self.marker)
        self.now = datetime.now(timezone.utc) - timedelta(minutes=1)

    async def observation(self, name, seconds=0, source='http_publico', available=True):
        return await self.conn.fetchval('''INSERT INTO hunter_price_observations(
            produto_id,nome,preco,coletado_em,fonte_coleta,fonte_url,disponivel)
            VALUES($1,$2,100,$3,$4,'https://example.com/nlp-fixture',$5) RETURNING id''',
            self.pid, name, self.now+timedelta(seconds=seconds), source, available)

    async def call(self, path):
        import app as backend
        from test_api import http
        async def db():
            yield self.conn
        backend.app.dependency_overrides[backend.get_db] = db
        try:
            return await http('GET', path)
        finally:
            backend.app.dependency_overrides.clear()

    async def test_result_is_persisted_and_idempotent(self):
        identity = await self.observation('Teclado Mecânico para Jogos')
        self.assertEqual(await process_event(self.conn, identity), 'processed')
        self.assertEqual(await process_event(self.conn, identity), 'duplicate')
        code, data = await self.call(f'/nlp/analises?produto_id={self.pid}')
        self.assertEqual(code, 200)
        self.assertEqual(len(data['resultados']), 1)
        self.assertEqual(data['resultados'][0]['category'], 'teclado')
        self.assertFalse(data['resultados'][0]['replay'])
        self.assertNotIn('para', data['resultados'][0]['tokens'])

    async def test_suggestions_normalize_accents_and_require_every_prefix(self):
        from urllib.parse import urlencode
        identity = await self.observation('Teclado Mecânico '+self.marker)
        await process_event(self.conn, identity)
        path = '/sugestoes?'+urlencode({'q':'MECÂN '+self.marker})
        code, data = await self.call(path)
        self.assertEqual(code, 200)
        self.assertEqual(len(data['sugestoes']), 1)
        self.assertEqual(data['sugestoes'][0]['categoria'], 'teclado')
        self.assertEqual((await self.call('/sugestoes?q='+self.marker+'+ausente'))[1]['sugestoes'], [])
        self.assertEqual((await self.call('/sugestoes?q=de+e+para'))[1]['sugestoes'], [])
        for path in ('/sugestoes?q=x', '/sugestoes?q=mouse&limite=11', '/nlp/analises?limite=0'):
            self.assertEqual((await self.call(path))[0], 422)

    async def test_only_latest_available_retail_is_suggested(self):
        first = await self.observation('Mouse '+self.marker)
        await process_event(self.conn, first)
        latest = await self.observation('Teclado '+self.marker, 1, available=False)
        await process_event(self.conn, latest)
        self.assertEqual((await self.call('/sugestoes?q='+self.marker))[1]['sugestoes'], [])
        await self.conn.execute("UPDATE hunter_catalog_products SET channel='b2b' WHERE id=$1", self.pid)
        self.assertEqual((await self.call('/sugestoes?q='+self.marker))[1]['sugestoes'], [])

    async def test_nlp_is_linked_to_numerical_mining(self):
        from data_mining.streaming import process_event as mine
        identity = await self.observation('Teclado '+self.marker)
        await process_event(self.conn, identity)
        await mine(self.conn, identity)
        code, data = await self.call('/analytics/categorias')
        self.assertEqual(code, 200)
        category = next(c for c in data['categorias'] if c['categoria'] == 'teclado')
        self.assertGreaterEqual(category['precos_analisados'], 1)

    async def test_trigger_excludes_fixture_and_is_atomic(self):
        fixture = await self.observation('Mouse ficticio', source='fixture_browser')
        self.assertFalse(await self.conn.fetchval('''SELECT EXISTS(SELECT 1
            FROM hunter_nlp_events WHERE observation_id=$1)''', fixture))
        nested = self.conn.transaction()
        await nested.start()
        identity = await self.observation('Mouse temporario', 1)
        await nested.rollback()
        self.assertEqual(await process_event(self.conn, identity), 'unknown')

    async def test_out_of_order_does_not_replace_latest_suggestion(self):
        latest = await self.observation('Teclado '+self.marker, 1)
        older = await self.observation('Mouse '+self.marker, 0)
        await process_event(self.conn, latest)
        await process_event(self.conn, older)
        data = (await self.call('/sugestoes?q='+self.marker))[1]
        self.assertEqual(data['sugestoes'][0]['categoria'], 'teclado')
