import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FlatList, Keyboard, Modal, Pressable, RefreshControl, ScrollView, Switch, Text, TextInput, View } from 'react-native';
import { useApp } from '../context/AppProvider';
import type { Product, SearchFilters } from '../api/types';
import { parseMoney } from '../lib/format';
import { Button, EmptyState, ErrorNotice, Field, Icon, ProductCard, Screen } from '../ui/components';
import { colors, styles } from '../ui/theme';

const categories = ['Mouse', 'Teclado', 'Monitor', 'Headset', 'Fone', 'Webcam', 'Microfone', 'Mousepad', 'Controle'];
const productKey = (item: Product) => `${item.loja}:${item.link}`;

export function CatalogScreen() {
  const { api, notice, dismissNotice } = useApp();
  const [text, setText] = useState('mouse');
  const [filters, setFilters] = useState<SearchFilters>({ query: 'mouse', order: 'priceAsc' });
  const [products, setProducts] = useState<Product[]>([]);
  const [shops, setShops] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterOpen, setFilterOpen] = useState(false);
  const sequence = useRef(0);
  const busy = useRef(false);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => { let active = true; void api.shops().then(result => { if (active) setShops(result.lojas); }).catch(() => {}); return () => { active = false; }; }, [api]);
  const load = useCallback(async (next = 1, append = false) => {
    controller.current?.abort();
    const abort = new AbortController(); controller.current = abort;
    const id = ++sequence.current;
    busy.current = true; setLoading(true); setLoadingMore(append); setError(null);
    try {
      const result = await api.search(filters, next, abort.signal);
      if (id !== sequence.current) return;
      setProducts(previous => append ? Array.from(new Map([...previous, ...result.produtos].map(p => [productKey(p), p])).values()) : result.produtos);
      setTotal(result.total); setPage(result.pagina);
      setHasMore(result.produtos.length > 0 && result.pagina * result.limite < result.total);
    } catch (err) {
      if (id === sequence.current && !abort.signal.aborted) setError(err instanceof Error ? err.message : 'Não foi possível buscar as ofertas.');
    } finally { if (id === sequence.current) { busy.current = false; setLoading(false); setLoadingMore(false); } }
  }, [api, filters]);
  useEffect(() => {
    setProducts([]); setTotal(0); setHasMore(false); setPage(1); void load();
    return () => { sequence.current += 1; controller.current?.abort(); busy.current = false; };
  }, [load]);
  const search = (query = text) => {
    if (!query.trim()) { setError('Digite o produto que deseja encontrar.'); return; }
    Keyboard.dismiss(); setText(query); setFilters(previous => ({ ...previous, query: query.trim() }));
  };
  const filterCount = [filters.store, filters.min != null, filters.max != null, filters.freeShipping].filter(Boolean).length;

  return <Screen>
    <FlatList data={products} numColumns={2} keyExtractor={productKey}
      contentContainerStyle={{ padding: 20, gap: 12, paddingBottom: 30 }} columnWrapperStyle={{ gap: 12 }}
      keyboardShouldPersistTaps="handled" renderItem={({ item }) => <ProductCard product={item} />}
      refreshControl={<RefreshControl refreshing={loading && !loadingMore && products.length > 0} onRefresh={() => void load()} tintColor={colors.green} />}
      onEndReachedThreshold={.4} onEndReached={() => { if (!busy.current && products.length > 0 && hasMore) void load(page + 1, true); }}
      ListHeaderComponent={<View style={{ gap: 20, paddingBottom: 16 }}>
        <View style={styles.between}><View style={styles.row}>
          <View style={{ backgroundColor: colors.lime, padding: 10, borderRadius: 15 }}><Icon name="radar" size={27} /></View>
          <Text style={{ color: colors.ink, fontSize: 27, fontWeight: '800', letterSpacing: -1.2 }}>hunter<Text style={{ color: colors.green }}>.</Text></Text>
        </View><View style={styles.badge}><Text style={styles.badgeText}>SEU RADAR DE OFERTAS</Text></View></View>
        <View style={{ gap: 9 }}><Text style={[styles.title, { fontSize: 36, maxWidth: 320 }]}>Seu próximo upgrade está aqui.</Text><Text style={styles.subtitle}>Compare lojas, acompanhe preços e encontre a oferta que faz sentido para você.</Text></View>
        <View style={[styles.row, { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.line, borderRadius: 17, paddingLeft: 15, gap: 6 }]}>
          <Icon name="magnify" color={colors.muted} />
          <TextInput accessibilityLabel="Buscar produtos" placeholder="Busque um periférico" placeholderTextColor={colors.muted} value={text} onChangeText={setText}
            maxLength={255} returnKeyType="search" onSubmitEditing={() => search()} style={{ flex: 1, color: colors.ink, minHeight: 56, fontSize: 15 }} />
          <Pressable accessibilityLabel="Pesquisar" accessibilityRole="button" onPress={() => search()} style={{ margin: 6, padding: 12, backgroundColor: colors.lime, borderRadius: 12 }}><Icon name="arrow-right" size={21} /></Pressable>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          {categories.map(category => <Pressable key={category} accessibilityRole="button" accessibilityState={{ selected: category.toLowerCase() === filters.query.toLowerCase() }} onPress={() => search(category.toLowerCase())}
            style={[styles.chip, category.toLowerCase() === filters.query.toLowerCase() && styles.chipActive]}><Text style={[styles.chipText, category.toLowerCase() === filters.query.toLowerCase() && { color: colors.white }]}>{category}</Text></Pressable>)}
        </ScrollView>
        {!!notice && <Pressable accessibilityRole="button" accessibilityLabel="Dispensar mensagem" onPress={dismissNotice} style={[styles.card, { backgroundColor: colors.pale }]}><Text style={styles.body}>{notice}</Text></Pressable>}
        <View style={styles.between}><View style={{ flex: 1, gap: 4 }}><Text style={styles.section}>Ofertas para você</Text><Text style={styles.small}>{loading && !products.length ? 'Consultando as lojas…' : `${total} resultados${filters.store ? ` · ${filters.store}` : ''}`}</Text></View>
          <Pressable accessibilityLabel="Filtrar e ordenar ofertas" accessibilityRole="button" onPress={() => setFilterOpen(true)} style={[styles.chip, styles.row, { gap: 6 }]}><Icon name="tune-variant" size={18} /><Text style={styles.chipText}>Filtros{filterCount ? ` (${filterCount})` : ''}</Text></Pressable>
        </View>
        <ErrorNotice message={error} onRetry={() => void load()} />
      </View>}
      ListEmptyComponent={loading ? <EmptyState title="Buscando suas ofertas" message="Consultando os produtos do catálogo Hunter." loading /> : !error ? <EmptyState icon="magnify-close" title="Nenhuma oferta encontrada" message="Experimente outro termo ou ajuste os filtros. Nem todas as lojas têm ofertas disponíveis." action={<Button title="Limpar filtros" secondary onPress={() => setFilters({ query: filters.query, order: 'priceAsc' })} />} /> : undefined}
      ListFooterComponent={products.length ? <View style={{ gap: 16, paddingTop: 8 }}>
        {hasMore && <Button title="Carregar mais ofertas" loading={loading} secondary onPress={() => void load(page + 1, true)} />}
        <Text style={[styles.small, { textAlign: 'center' }]}>Preços observados nas lojas. Confira preço e estoque antes de comprar.</Text>
      </View> : undefined}
    />
    <FilterSheet visible={filterOpen} close={() => setFilterOpen(false)} filters={filters} shops={shops} apply={setFilters} />
  </Screen>;
}

function FilterSheet({ visible, close, filters, shops, apply }: { visible: boolean; close: () => void; filters: SearchFilters; shops: string[]; apply: (f: SearchFilters) => void }) {
  const [store, setStore] = useState(''); const [min, setMin] = useState(''); const [max, setMax] = useState('');
  const [order, setOrder] = useState<'priceAsc' | 'priceDesc'>('priceAsc'); const [free, setFree] = useState(false); const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (visible) { setStore(filters.store ?? ''); setMin(filters.min == null ? '' : String(filters.min).replace('.', ',')); setMax(filters.max == null ? '' : String(filters.max).replace('.', ',')); setOrder(filters.order ?? 'priceAsc'); setFree(!!filters.freeShipping); setError(null); } }, [visible, filters]);
  const submit = () => {
    try {
      const lower = parseMoney(min), upper = parseMoney(max);
      if (lower != null && upper != null && lower > upper) throw new Error('O preço mínimo deve ser menor que o máximo.');
      apply({ query: filters.query, store: store || undefined, min: lower, max: upper, order, freeShipping: free }); close();
    } catch (err) { setError((err as Error).message); }
  };
  return <Modal visible={visible} transparent animationType="slide" onRequestClose={close}>
    <View style={{ flex: 1, justifyContent: 'flex-end', backgroundColor: '#18231d66' }}>
      <Pressable accessibilityLabel="Fechar filtros" accessibilityRole="button" onPress={close} style={{ flex: 1, minHeight: 32 }} />
      <View style={{ backgroundColor: colors.paper, borderTopLeftRadius: 26, borderTopRightRadius: 26, maxHeight: '88%' }}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.content, { paddingBottom: 40 }]}>
          <View style={styles.between}><Text style={styles.section}>Do seu jeito</Text><Pressable accessibilityRole="button" accessibilityLabel="Fechar" onPress={close} style={{ padding: 12 }}><Icon name="close" /></Pressable></View>
          <Text style={styles.body}>Loja</Text><View style={[styles.row, { flexWrap: 'wrap', gap: 8 }]}>{['', ...shops].map(item => <Pressable accessibilityRole="button" key={item} onPress={() => setStore(item)} style={[styles.chip, store === item && styles.chipActive]}><Text style={[styles.chipText, store === item && { color: colors.white }]}>{item || 'Todas as lojas'}</Text></Pressable>)}</View>
          <View style={styles.row}><View style={{ flex: 1 }}><Field label="Mínimo (R$)" value={min} onChangeText={setMin} keyboardType="decimal-pad" placeholder="0,00" /></View><View style={{ flex: 1 }}><Field label="Máximo (R$)" value={max} onChangeText={setMax} keyboardType="decimal-pad" placeholder="Sem limite" /></View></View>
          <Text style={styles.body}>Ordenar por</Text><View style={styles.row}>{(['priceAsc', 'priceDesc'] as const).map(item => <Pressable accessibilityRole="button" key={item} onPress={() => setOrder(item)} style={[styles.chip, order === item && styles.chipActive]}><Text style={[styles.chipText, order === item && { color: colors.white }]}>{item === 'priceAsc' ? 'Menor preço' : 'Maior preço'}</Text></Pressable>)}</View>
          <View style={styles.between}><Text style={styles.body}>Só frete grátis anunciado</Text><Switch accessibilityLabel="Somente frete grátis" value={free} onValueChange={setFree} trackColor={{ true: colors.green }} /></View>
          <ErrorNotice message={error} /><Button title="Aplicar filtros" onPress={submit} />
          <Button title="Limpar filtros" secondary onPress={() => { setStore(''); setMin(''); setMax(''); setOrder('priceAsc'); setFree(false); }} />
        </ScrollView>
      </View>
    </View>
  </Modal>;
}
