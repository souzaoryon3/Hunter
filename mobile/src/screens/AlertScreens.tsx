import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, FlatList, KeyboardAvoidingView, Platform, Pressable, RefreshControl, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp, NativeStackScreenProps } from '@react-navigation/native-stack';
import type { RootStackParams } from '../navigation/types';
import { useApp } from '../context/AppProvider';
import { useResource } from '../hooks/useResource';
import type { PriceAlert } from '../api/types';
import { currency, parseMoney } from '../lib/format';
import { Button, EmptyState, ErrorNotice, Field, FormScroll, Guest, Header, Icon, Screen, openProduct } from '../ui/components';
import { colors, styles } from '../ui/theme';

export function AlertsScreen() {
  const { api, authenticated } = useApp();
  const currentApi = useRef(api); currentApi.current = api;
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  const load = useCallback(() => api.alerts(), [api]);
  const resource = useResource(load, authenticated);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  useEffect(() => { setError(null); setDeleting(null); }, [api]);
  const remove = (item: PriceAlert) => Alert.alert('Excluir este alerta?', item.produto, [
    { text: 'Cancelar', style: 'cancel' },
    { text: 'Excluir', style: 'destructive', onPress: () => {
      setDeleting(item.id); setError(null);
      void api.deleteAlert(item.id).then(() => { if (currentApi.current === api) return resource.refresh(); })
        .catch(err => { if (currentApi.current === api) setError(err.message); })
        .finally(() => { if (currentApi.current === api) setDeleting(null); });
    } },
  ]);
  return <Screen><Header title="Seu radar de preços" subtitle="Você escolhe o preço. O Hunter acompanha." right={authenticated ? <Pressable accessibilityRole="button" accessibilityLabel="Criar alerta" onPress={() => navigation.navigate('AlertForm')} style={{ backgroundColor: colors.lime, padding: 12, borderRadius: 16 }}><Icon name="plus" /></Pressable> : undefined} />
    {!authenticated ? <Guest title="Deixe o preço vir até você." /> : <FlatList data={resource.data ?? []} keyExtractor={item => String(item.id)}
      contentContainerStyle={[styles.content, { gap: 14 }]} refreshControl={<RefreshControl refreshing={resource.loading} onRefresh={() => void resource.refresh()} tintColor={colors.green} />}
      ListHeaderComponent={<ErrorNotice message={error || resource.error} onRetry={() => void resource.refresh()} />}
      ListEmptyComponent={<EmptyState icon="bell-ring-outline" title={resource.loading ? 'Carregando seu radar' : 'Seu primeiro alerta está por aqui.'} loading={resource.loading}
        message={resource.error ? undefined : 'Escolha o produto e o preço que deseja pagar. As ofertas encontradas aparecerão nas suas notificações.'}
        action={!resource.loading && !resource.error ? <Button title="Criar meu primeiro alerta" onPress={() => navigation.navigate('AlertForm')} /> : undefined} />}
      renderItem={({ item }) => <View style={styles.card}>
        <View style={styles.between}><View style={[styles.badge, item.atingido && { backgroundColor: colors.lime }]}><Text style={styles.badgeText}>{item.atingido ? 'PREÇO ATINGIDO' : 'ACOMPANHANDO'}</Text></View><Icon name="radar" color={colors.green} /></View>
        <Text style={[styles.body, { fontWeight: '700' }]}>{item.produto}</Text>
        <View style={styles.between}><View style={{ gap: 3 }}><Text style={styles.small}>Quero pagar até</Text><Text style={[styles.section, { fontSize: 25 }]}>{currency(item.preco)}</Text></View><View style={{ alignItems: 'flex-end', gap: 3 }}><Text style={styles.small}>Menor oferta atual</Text><Text style={{ color: colors.green, fontSize: 19, fontWeight: '700' }}>{item.preco_atual == null ? 'Ainda sem oferta' : currency(item.preco_atual)}</Text>{item.loja && <Text style={styles.small}>{item.loja}</Text>}</View></View>
        <View style={styles.divider} /><View style={styles.between}>
          <Pressable accessibilityRole="button" accessibilityLabel={`Editar alerta de ${item.produto}`} onPress={() => navigation.navigate('AlertForm', { alert: item })} style={[styles.row, { paddingVertical: 10 }]}><Icon name="pencil-outline" size={18} /><Text style={styles.chipText}>Editar</Text></Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel={`Excluir alerta de ${item.produto}`} disabled={deleting != null} onPress={() => remove(item)} style={{ padding: 10 }}><Icon name="trash-can-outline" color={colors.danger} size={20} /></Pressable>
        </View>
        {item.link && <Button title="Ver oferta atual" secondary onPress={() => { void openProduct(item.link).catch(err => setError(err.message)); }} />}
      </View>} />}
  </Screen>;
}

export function AlertFormScreen({ route, navigation }: NativeStackScreenProps<RootStackParams, 'AlertForm'>) {
  const { api, authenticated } = useApp();
  const existing = route.params?.alert;
  const editingApi = useRef(authenticated ? api : null);
  useEffect(() => { if (!editingApi.current && authenticated) editingApi.current = api; }, [api, authenticated]);
  const staleEdit = editingApi.current !== null && editingApi.current !== api;
  const [product, setProduct] = useState((existing?.produto ?? route.params?.product ?? '').slice(0, 255));
  const [price, setPrice] = useState(existing ? String(existing.preco).replace('.', ',') : '');
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setError(null);
    try {
      if (staleEdit) throw new Error('A sessão mudou. Abra o alerta novamente na sua conta.');
      if (!product.trim()) throw new Error('Informe o nome do produto.');
      const amount = parseMoney(price);
      if (amount == null || amount <= 0) throw new Error('Informe o preço que deseja pagar, maior que zero.');
      setBusy(true);
      if (existing) await api.updateAlert(existing.id, product, amount);
      else await api.createAlert(product, amount);
      navigation.goBack();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return <Screen><Header title={existing ? 'Editar alerta' : 'Novo alerta'} back />{!authenticated ? <Guest message="Entre para salvar seu alerta. Ele ficará disponível também na sua conta pelo computador." /> : staleEdit ? <EmptyState title="Abra o alerta novamente" message="Sua sessão mudou. Volte aos alertas para continuar com a conta atual." action={<Button title="Voltar" onPress={() => navigation.goBack()} />} /> : <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}><FormScroll>
    <View style={[styles.card, { backgroundColor: colors.pale }]}><Icon name="radar" color={colors.green} size={32} /><Text style={styles.section}>O seu preço, no seu tempo.</Text><Text style={styles.subtitle}>O Hunter compara o nome informado com as ofertas do catálogo. Seja específico para acompanhar o produto certo.</Text></View>
    <Field label="Produto para acompanhar" value={product} onChangeText={setProduct} maxLength={255} editable={!busy} placeholder="Ex.: Teclado Logitech MX Keys" />
    <Field label="Quero pagar até (R$)" value={price} onChangeText={setPrice} keyboardType="decimal-pad" placeholder="199,90" editable={!busy} />
    <ErrorNotice message={error} /><Button title={existing ? 'Salvar alterações' : 'Ativar meu alerta'} icon="bell-plus-outline" onPress={() => void save()} loading={busy} />
    <Text style={styles.small}>As ofertas encontradas aparecem na aba Notificações. A disponibilidade depende dos preços observados pelo Hunter.</Text>
  </FormScroll></KeyboardAvoidingView>}</Screen>;
}
