import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';
import { useApp } from '../context/AppProvider';
import { useResource } from '../hooks/useResource';
import { currency, date } from '../lib/format';
import { Button, EmptyState, ErrorNotice, Guest, Header, Icon, Screen, openProduct } from '../ui/components';
import { colors, styles } from '../ui/theme';

export function NotificationsScreen() {
  const { api, authenticated } = useApp();
  const currentApi = useRef(api); currentApi.current = api;
  const load = useCallback(() => api.notifications(), [api]);
  const resource = useResource(load, authenticated);
  const [error, setError] = useState<string | null>(null); const [more, setMore] = useState(false); const [reading, setReading] = useState<number | null>(null);
  useEffect(() => { setError(null); setMore(false); setReading(null); }, [api]);
  const mark = async (id: number) => {
    setReading(id); setError(null);
    try {
      await api.readNotification(id);
      if (currentApi.current === api) resource.setData(previous => {
        if (!previous) return previous;
        const unread = previous.notificacoes.some(item => item.id === id && !item.read_at);
        return { ...previous, nao_lidas: Math.max(0, previous.nao_lidas - Number(unread)), notificacoes: previous.notificacoes.map(item => item.id === id ? { ...item, read_at: item.read_at ?? new Date().toISOString() } : item) };
      });
    } catch (err) { if (currentApi.current === api) setError((err as Error).message); }
    finally { if (currentApi.current === api) setReading(null); }
  };
  const next = async () => {
    if (!resource.data || more) return;
    setMore(true); setError(null);
    try {
      const data = await api.notifications(resource.data.pagina + 1);
      if (currentApi.current === api) resource.setData(previous => previous ? { ...data, notificacoes: Array.from(new Map([...previous.notificacoes, ...data.notificacoes].map(item => [item.id, item])).values()) } : data);
    } catch (err) { if (currentApi.current === api) setError((err as Error).message); }
    finally { if (currentApi.current === api) setMore(false); }
  };
  return <Screen><Header title="Boas notícias" subtitle={authenticated && resource.data ? `${resource.data.nao_lidas} notificações não lidas` : 'As novidades dos seus alertas, por aqui.'} />
    {!authenticated ? <Guest title="Nenhuma boa oferta passa despercebida." /> : <FlatList data={resource.data?.notificacoes ?? []} keyExtractor={item => String(item.id)} contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={resource.loading} onRefresh={() => void resource.refresh()} tintColor={colors.green} />}
      ListHeaderComponent={<ErrorNotice message={error || resource.error} onRetry={() => void resource.refresh()} />}
      ListEmptyComponent={<EmptyState icon="bell-check-outline" title={resource.loading ? 'Carregando novidades' : 'Por enquanto, tudo tranquilo.'} loading={resource.loading} message={resource.error ? undefined : 'Quando um alerta encontrar o preço que você quer, a oferta aparece aqui. Puxe a tela para atualizar.'} />}
      renderItem={({ item }) => <View style={[styles.card, !item.read_at && { borderColor: colors.green }]}>
        <View style={styles.between}><View style={styles.row}><Icon name="tag-heart-outline" color={colors.green} /><Text style={styles.badgeText}>{item.loja}</Text></View>{!item.read_at && <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.green }} />}</View>
        <Text style={[styles.body, { fontWeight: '700' }]}>{item.produto}</Text><Text style={[styles.section, { fontSize: 28 }]}>{currency(item.preco)}</Text>
        <Text style={styles.small}>Seu preço desejado: {currency(item.preco_desejado)} · {date(item.created_at)}</Text>
        <Button title="Ver oferta na loja" secondary icon="open-in-new" onPress={() => { void openProduct(item.link).catch(err => setError(err.message)); }} />
        {!item.read_at && <Pressable accessibilityRole="button" disabled={reading != null} onPress={() => void mark(item.id)} style={{ paddingVertical: 12 }}><Text style={{ color: colors.green, textAlign: 'center', fontWeight: '600' }}>{reading === item.id ? 'Atualizando…' : 'Marcar como lida'}</Text></Pressable>}
      </View>}
      ListFooterComponent={resource.data && resource.data.pagina * resource.data.limite < resource.data.total ? <Button title="Carregar mais notificações" loading={more} onPress={() => void next()} /> : undefined} />}
  </Screen>;
}
