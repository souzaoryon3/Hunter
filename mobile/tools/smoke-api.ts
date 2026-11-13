import assert from 'node:assert/strict';
import { createApi, normalizeApiUrl } from '../src/api/client';

async function main() {
  const base = normalizeApiUrl(process.argv[2] || 'http://127.0.0.1:18088', true);
  const api = createApi(base, null, () => {});
  assert.equal((await api.health()).status, 'ready');
  const stores = (await api.shops()).lojas;
  assert.ok(stores.length > 0);
  for (const store of ['KaBuM!', 'Pichau', 'TerabyteShop', 'Amazon Brasil', 'Fast Shop']) {
    assert.ok(stores.includes(store));
    const result = await api.search({ query: 'mouse', store }, 1);
    assert.ok(result.produtos.length > 0 && result.total > 0);
    const product = result.produtos.find(item => item.produto_id && item.historico_disponivel);
    assert.ok(product?.produto_id);
    const history = await api.history(product.produto_id);
    assert.ok(history.total > 0 && history.historico.length > 0);
    console.log(`${store}: busca e histórico compatíveis com o cliente mobile.`);
  }
  console.log('Contrato HTTP real validado sem gravar dados.');
}
void main().catch(error => { console.error(error instanceof Error ? error.message : 'Falha no contrato da API.'); process.exitCode = 1; });
