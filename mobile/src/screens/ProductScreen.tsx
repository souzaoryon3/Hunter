import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParams } from '../navigation/types';
import { useApp } from '../context/AppProvider';
import { useResource } from '../hooks/useResource';
import { currency, date } from '../lib/format';
import { Button, ErrorNotice, FormScroll, Header, Icon, ProductImage, Screen, openProduct } from '../ui/components';
import { colors, styles } from '../ui/theme';

export function ProductScreen({ route, navigation }: NativeStackScreenProps<RootStackParams, 'Product'>) {
  const { product } = route.params;
  const { api } = useApp();
  const currentApi = useRef(api); currentApi.current = api;
  const load = useCallback(() => api.history(product.produto_id!), [api, product.produto_id]);
  const history = useResource(load, !!product.produto_id && product.historico_disponivel);
  const [error, setError] = useState<string | null>(null); const [more, setMore] = useState(false);
  useEffect(() => { setError(null); setMore(false); }, [api]);
  const next = async () => {
    if (!product.produto_id || !history.data || more) return;
    setMore(true);
    try {
      const data = await api.history(product.produto_id, history.data.pagina + 1);
      if (currentApi.current === api) history.setData(previous => previous ? { ...data, historico: Array.from(new Map([...previous.historico, ...data.historico].map(item => [item.id, item])).values()) } : data);
    } catch (err) { if (currentApi.current === api) setError((err as Error).message); }
    finally { if (currentApi.current === api) setMore(false); }
  };
  return <Screen><Header title="Olhe de perto" back /><FormScroll>
    <View style={[styles.card, { padding: 14 }]}><ProductImage uri={product.imagem_url} large /></View>
    <View style={styles.badge}><Text style={styles.badgeText}>{product.loja}</Text></View>
    <Text style={[styles.section, { fontSize: 22, lineHeight: 30 }]}>{product.nome}</Text>
    <View style={{ gap: 7 }}><Text style={{ color: colors.ink, fontSize: 40, letterSpacing: -1.5, fontWeight: '800' }}>{currency(product.preco)}</Text>
      {product.pagamento && <Text style={styles.subtitle}>{product.pagamento}</Text>}
      {product.preco_cartao != null && <Text style={styles.small}>{currency(product.preco_cartao)} no cartão; confirme as condições na loja.</Text>}
      {product.price_kind === 'promotional' && <Text style={styles.small}>Promoção: {product.promotion_terms || 'Confira as condições na loja.'}</Text>}
    </View>
    <Button title={`Ver na ${product.loja}`} icon="open-in-new" onPress={() => { void openProduct(product.link).catch(err => setError(err.message)); }} />
    <Button title="Criar alerta de preço" secondary icon="bell-plus-outline" onPress={() => navigation.navigate('AlertForm', { product: product.nome })} />
    <View style={styles.card}><View style={styles.row}><Icon name="clock-outline" color={colors.green} /><Text style={styles.body}>Observado em {date(product.coletado_em)}</Text></View>
      <Text style={styles.small}>{product.frete_observacao || (product.frete_gratis ? 'Frete grátis anunciado; confirme regras e CEP.' : 'Consulte o frete conforme seu CEP na loja.')}</Text>
      <Text style={styles.small}>O valor registrado pode mudar. Confira preço e estoque antes de comprar.</Text></View>
    <ErrorNotice message={error} /><Text style={styles.section}>O caminho deste preço</Text>
    <ErrorNotice message={history.error} onRetry={() => void history.refresh()} />
    {history.loading && !history.data && <Text style={styles.subtitle}>Carregando o histórico…</Text>}
    {history.data?.historico.map((item, index) => <View key={item.id} style={[styles.card, { paddingVertical: 14 }]}>
      <View style={styles.between}><View style={{ flex: 1, gap: 5 }}><Text style={styles.small}>{date(item.coletado_em)}</Text><Text style={[styles.body, { color: item.disponivel ? colors.green : colors.muted }]}>{item.disponivel ? 'Oferta observada' : 'Indisponível nesta observação'}</Text></View><Text style={[styles.section, { fontSize: 22 }]}>{currency(item.preco)}</Text></View>
      {index === 0 && <Text style={styles.small}>Registro mais recente</Text>}
    </View>)}
    {!product.produto_id || !product.historico_disponivel ? <Text style={styles.subtitle}>Esta oferta ainda não tem um histórico de coleta disponível.</Text> : history.data && history.data.historico.length === 0 ? <Text style={styles.subtitle}>Ainda não há observações para este produto.</Text> : null}
    {history.data && history.data.pagina * history.data.limite < history.data.total && <Button title="Ver registros anteriores" secondary loading={more} onPress={() => void next()} />}
  </FormScroll></Screen>;
}
