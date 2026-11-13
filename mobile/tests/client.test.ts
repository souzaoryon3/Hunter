import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createApi, ApiError, normalizeApiUrl } from '../src/api/client';
import { currency, parseMoney, safeProductUrl, validatePassword } from '../src/lib/format';

const ok = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

test('URL da API rejeita credenciais, caminhos, queries e HTTP em release', () => {
  assert.equal(normalizeApiUrl(' http://10.0.2.2:18088/ ', true), 'http://10.0.2.2:18088');
  for (const url of ['http://localhost:18088', 'https://user:password@example.invalid', 'https://example.invalid/login', 'https://example.invalid?token=secret', 'file:///tmp/app']) {
    assert.throws(() => normalizeApiUrl(url, false), ApiError);
  }
  assert.equal(normalizeApiUrl('https://api.example.invalid/', false), 'https://api.example.invalid');
});

test('login segue o formulario OAuth da API sem enviar JWT anterior', async () => {
  const transport: typeof fetch = async (url, options) => {
    assert.equal(url, 'https://api.example.invalid/login');
    assert.equal(options?.method, 'POST');
    assert.equal(new Headers(options?.headers).get('Content-Type'), 'application/x-www-form-urlencoded');
    assert.equal(new Headers(options?.headers).get('Authorization'), null);
    const form = new URLSearchParams(String(options?.body));
    assert.equal(form.get('username'), 'user@example.invalid');
    assert.equal(form.get('password'), 'fixture&password');
    return ok({ access_token: 'fixture-token' });
  };
  const api = createApi('https://api.example.invalid', 'old-fixture-token', () => assert.fail('Login não expira outra sessão'), transport);
  assert.equal((await api.login(' user@example.invalid ', 'fixture&password')).access_token, 'fixture-token');
});

test('busca preserva filtros, zero, ordem e pagina sem enviar credenciais', async () => {
  const transport: typeof fetch = async (input, options) => {
    const url = new URL(String(input));
    assert.equal(url.pathname, '/buscar-produtos');
    assert.equal(url.searchParams.get('nome'), 'mouse gamer');
    assert.equal(url.searchParams.get('loja'), 'KaBuM!');
    assert.equal(url.searchParams.get('preco_min'), '0');
    assert.equal(url.searchParams.get('preco_max'), '150.5');
    assert.equal(url.searchParams.get('pagina'), '3');
    assert.equal(url.searchParams.get('ordem'), 'priceDesc');
    assert.equal(url.searchParams.get('frete_gratis'), 'true');
    assert.equal(new Headers(options?.headers).get('Authorization'), null);
    return ok({ produtos: [], total: 0, pagina: 3, limite: 20 });
  };
  await createApi('https://api.example.invalid', 'fixture-token', () => {}, transport).search({ query: 'mouse gamer', store: 'KaBuM!', min: 0, max: 150.5, order: 'priceDesc', freeShipping: true }, 3);
});

test('recursos privados exigem JWT e expiram sessao em 401, inclusive HTML', async () => {
  let called = 0, expired = 0;
  const transport: typeof fetch = async (_url, options) => {
    called += 1;
    assert.equal(new Headers(options?.headers).get('Authorization'), 'Bearer fixture-token');
    return new Response('<h1>Unauthorized</h1>', { status: 401 });
  };
  await assert.rejects(createApi('https://api.example.invalid', null, () => {}, transport).alerts(), (err: ApiError) => err.status === 401);
  assert.equal(called, 0);
  await assert.rejects(createApi('https://api.example.invalid', 'fixture-token', () => { expired += 1; }, transport).profile(), (err: ApiError) => err.status === 401);
  assert.equal(expired, 1);
});

test('422 mostra apenas mensagens de validacao, sem refletir dados sensiveis', async () => {
  const transport: typeof fetch = async () => ok({ detail: [{ msg: 'Senha fora do limite', input: 'sensitive-fixture-do-not-display' }] }, 422);
  await assert.rejects(createApi('https://api.example.invalid', null, () => {}, transport).register('Usuario', 'u@example.invalid', 'fixture-password'), (err: ApiError) => err.message === 'Senha fora do limite' && !err.message.includes('sensitive-fixture'));
});

test('alertas usam JSON, identidade do recurso e token autenticado', async () => {
  const calls: string[] = [];
  const transport: typeof fetch = async (url, options) => {
    calls.push(`${options?.method} ${url}`);
    assert.equal(new Headers(options?.headers).get('Authorization'), 'Bearer fixture-token');
    if (options?.method !== 'DELETE') assert.deepEqual(JSON.parse(String(options?.body)), { produto: 'Mouse', preco: 99.9 });
    return ok({ id: 7, message: 'ok' });
  };
  const api = createApi('https://api.example.invalid', 'fixture-token', () => {}, transport);
  await api.createAlert(' Mouse ', 99.9); await api.updateAlert(7, 'Mouse', 99.9); await api.deleteAlert(7);
  assert.deepEqual(calls, ['POST https://api.example.invalid/alerta-preco', 'PUT https://api.example.invalid/alerta/7', 'DELETE https://api.example.invalid/alerta/7']);
});

test('interrupcao de busca nao vira erro de sessao nem deixa requisicao antiga ativa', async () => {
  const controller = new AbortController();
  const transport: typeof fetch = async (_url, options) => new Promise((_resolve, reject) => {
    options?.signal?.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
  });
  const pending = createApi('https://api.example.invalid', null, () => assert.fail(), transport).search({ query: 'mouse' }, 1, controller.signal);
  controller.abort(); await assert.rejects(pending, /aborted/);
});

test('servidor desconectado e resposta invalida geram mensagens acionaveis', async () => {
  const offline: typeof fetch = async () => { throw new Error('socket'); };
  await assert.rejects(createApi('https://api.example.invalid', null, () => {}, offline).shops(), /Não foi possível conectar/);
  const html: typeof fetch = async () => new Response('<html>proxy</html>');
  await assert.rejects(createApi('https://api.example.invalid', null, () => {}, html).health(), /resposta válida/);
  await assert.rejects(createApi('', null, () => {}, offline).health(), /Configure o endereço/);
});

test('valores brasileiros nao aceitam parcelas, lixo ou precisao excessiva', () => {
  assert.equal(parseMoney('R$ 1.234,56'), 1234.56); assert.equal(parseMoney('99.90'), 99.9);
  assert.equal(parseMoney('0'), 0); assert.equal(parseMoney(''), undefined);
  for (const value of ['12x 19,90', '-1', 'abc', '1,234', '1.234', '1.2,3', 'Infinity']) assert.throws(() => parseMoney(value));
  assert.match(currency(99.9), /99,90/);
});

test('links externos aceitam somente ofertas HTTPS sem credenciais', () => {
  assert.equal(safeProductUrl('https://example.invalid/produto'), 'https://example.invalid/produto');
  for (const value of ['javascript:alert(1)', 'http://example.invalid', 'https://user:password@example.invalid', 'file:///etc/passwd']) assert.equal(safeProductUrl(value), null);
});

test('senha respeita o limite em bytes do backend, inclusive Unicode', () => {
  assert.doesNotThrow(() => validatePassword('fixture-password'));
  assert.doesNotThrow(() => validatePassword('á'.repeat(36)));
  assert.throws(() => validatePassword('á'.repeat(37)));
  assert.throws(() => validatePassword('short'));
});

test('APK de teste aceita HTTP apenas na rede privada ou loopback', () => {
  for (const url of ['http://192.168.15.28:18089', 'http://10.0.2.2:18088', 'http://172.16.0.4:8000', 'http://localhost:18088']) {
    assert.ok(normalizeApiUrl(url, true, true).startsWith('http://'));
  }
  for (const url of ['http://example.com', 'http://8.8.8.8', 'http://192.169.0.1', 'http://172.32.0.1', 'http://127.0.0.1.example.com']) {
    assert.throws(() => normalizeApiUrl(url, true, true), ApiError);
  }
  assert.equal(normalizeApiUrl('https://api.example.invalid', false, true), 'https://api.example.invalid');
});
