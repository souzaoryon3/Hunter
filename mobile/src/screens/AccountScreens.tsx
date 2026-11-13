import React, { useEffect, useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, Pressable, Text, View } from 'react-native';
import type { NativeStackScreenProps, NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useNavigation } from '@react-navigation/native';
import type { RootStackParams } from '../navigation/types';
import { useApp } from '../context/AppProvider';
import { createApi } from '../api/client';
import { ALLOW_LOCAL_HTTP, normalizeNativeApiUrl } from '../lib/config';
import { validatePassword } from '../lib/format';
import { ActionRow, Button, EmptyState, ErrorNotice, Field, FormScroll, Guest, Header, Icon, Screen } from '../ui/components';
import { colors, styles } from '../ui/theme';

const validEmail = (value: string) => /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(value.trim());
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Não foi possível concluir a operação.';

export function AuthScreen({ navigation, route }: NativeStackScreenProps<RootStackParams, 'Auth'>) {
  const { api, login, endpoint } = useApp();
  const [register, setRegister] = useState(!!route.params?.register);
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null);
  useEffect(() => { setPassword(''); setEmail(''); setError(null); }, [endpoint]);
  const submit = async () => {
    setError(null);
    try {
      if (!validEmail(email)) throw new Error('Informe um e-mail válido.');
      if (!password) throw new Error('Informe sua senha.');
      if (register) { if (name.trim().length < 2) throw new Error('Informe seu nome, com ao menos 2 caracteres.'); validatePassword(password); }
      setLoading(true);
      if (register) { await api.register(name, email, password); setRegister(false); }
      await login(email, password);
      setPassword(''); navigation.goBack();
    } catch (err) { setError(errorMessage(err)); }
    finally { setLoading(false); }
  };
  return <Screen><KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <Header title={register ? 'Crie sua conta' : 'Bom ter você aqui.'} back />
    <FormScroll>
      <View style={{ width: 70, height: 70, borderRadius: 24, backgroundColor: colors.lime, alignItems: 'center', justifyContent: 'center' }}><Icon name="radar" size={36} /></View>
      <Text style={styles.subtitle}>{register ? 'Um só Hunter para comparar preços e acompanhar suas ofertas, no celular e no computador.' : 'Acesse os mesmos alertas e notificações da sua conta Hunter.'}</Text>
      {register && <Field label="Seu nome" value={name} onChangeText={setName} autoComplete="name" textContentType="name" maxLength={255} editable={!loading} />}
      <Field label="E-mail" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} autoComplete="email" textContentType="emailAddress" maxLength={255} editable={!loading} />
      <Field label="Senha" value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" autoCorrect={false}
        autoComplete={register ? 'new-password' : 'current-password'} textContentType={register ? 'newPassword' : 'password'}
        hint={register ? 'Ao menos 8 caracteres. Sua senha é protegida pelo Hunter.' : undefined} editable={!loading} onSubmitEditing={() => void submit()} />
      <ErrorNotice message={error} />
      <Button title={register ? 'Criar minha conta' : 'Entrar no Hunter'} onPress={() => void submit()} loading={loading} disabled={!endpoint} />
      <Button secondary title={register ? 'Já tenho uma conta' : 'Quero criar uma conta'} disabled={loading} onPress={() => { setRegister(!register); setError(null); }} />
      <Pressable accessibilityRole="button" disabled={loading} onPress={() => navigation.navigate('Connection')} style={{ padding: 15 }}><Text style={[styles.small, { textAlign: 'center', textDecorationLine: 'underline' }]}>Configurar conexão com o Hunter</Text></Pressable>
    </FormScroll>
  </KeyboardAvoidingView></Screen>;
}

export function AccountScreen() {
  const { authenticated, user, authError, refreshUser, logout, endpoint } = useApp();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const signOut = () => Alert.alert('Sair da sua conta?', 'Seus alertas continuam salvos no Hunter.', [
    { text: 'Cancelar', style: 'cancel' }, { text: 'Sair', onPress: () => { setBusy(true); void logout().catch(err => setError(errorMessage(err))).finally(() => setBusy(false)); } },
  ]);
  return <Screen><Header title="Sua conta" subtitle="Seu Hunter, em qualquer lugar." /><FormScroll>
    {authenticated ? <View style={styles.card}>
      <View style={styles.row}><View style={{ width: 56, height: 56, borderRadius: 20, backgroundColor: colors.lime, alignItems: 'center', justifyContent: 'center' }}><Icon name="account-outline" size={30} /></View>
        <View style={{ flex: 1, gap: 3 }}><Text style={styles.section}>{user?.nome ?? 'Sua conta Hunter'}</Text><Text style={styles.small}>{user?.email ?? 'Carregando seus dados…'}</Text></View></View>
      <ErrorNotice message={authError} onRetry={() => { void refreshUser().catch(err => setError(errorMessage(err))); }} />
      <ActionRow icon="account-edit-outline" title="Editar perfil" subtitle="Nome, e-mail e senha" onPress={() => navigation.navigate('Profile')} />
    </View> : <Guest />}
    <View style={styles.card}><Text style={styles.section}>Preferências</Text>
      <ActionRow icon="connection" title="Conexão com o Hunter" subtitle={endpoint || 'Defina o endereço do servidor'} onPress={() => navigation.navigate('Connection')} />
    </View>
    <View style={[styles.card, { backgroundColor: colors.pale }]}><Icon name="shield-check-outline" color={colors.green} /><Text style={[styles.body, { fontWeight: '600' }]}>Tudo na sua conta.</Text><Text style={styles.subtitle}>Ofertas, histórico e alertas são sincronizados com o Hunter. Confira as condições na loja antes de comprar.</Text></View>
    <ErrorNotice message={error} />
    {authenticated && <Button title="Sair da conta" secondary onPress={signOut} loading={busy} />}
    <Text style={[styles.small, { textAlign: 'center' }]}>Hunter Mobile · 1.0.0</Text>
  </FormScroll></Screen>;
}

export function ProfileScreen({ navigation }: NativeStackScreenProps<RootStackParams, 'Profile'>) {
  const { authenticated, user, updateProfile } = useApp();
  const [name, setName] = useState(user?.nome ?? ''); const [email, setEmail] = useState(user?.email ?? '');
  const [password, setPassword] = useState(''); const [current, setCurrent] = useState('');
  const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null);
  useEffect(() => { setName(user?.nome ?? ''); setEmail(user?.email ?? ''); setPassword(''); setCurrent(''); }, [user]);
  const save = async () => {
    setError(null);
    try {
      if (name.trim().length < 2 || !validEmail(email)) throw new Error('Confira seu nome e e-mail.');
      const changes: Parameters<typeof updateProfile>[0] = {};
      if (name.trim() !== user?.nome) changes.nome = name.trim();
      if (email.trim() !== user?.email) changes.email = email.trim();
      if (password) { validatePassword(password); changes.senha = password; }
      if ((changes.email || changes.senha) && !current) throw new Error('Confirme sua senha atual para alterar e-mail ou senha.');
      if (!Object.keys(changes).length) throw new Error('Altere algum campo antes de salvar.');
      if (current) changes.senha_atual = current;
      setLoading(true); await updateProfile(changes); setPassword(''); setCurrent(''); navigation.goBack();
    } catch (err) { setError(errorMessage(err)); } finally { setLoading(false); }
  };
  return <Screen><Header title="Editar perfil" back />{!authenticated ? <Guest /> : !user ? <EmptyState title="Carregando seus dados" message="Se a conexão estiver indisponível, volte à Conta e tente atualizar o perfil." loading /> : <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}><FormScroll>
    <Field label="Nome" value={name} onChangeText={setName} maxLength={255} editable={!!user && !loading} />
    <Field label="E-mail" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} maxLength={255} editable={!!user && !loading} />
    <Field label="Nova senha (opcional)" value={password} onChangeText={setPassword} secureTextEntry autoComplete="new-password" editable={!!user && !loading} />
    <Field label="Senha atual" value={current} onChangeText={setCurrent} secureTextEntry autoComplete="current-password" hint="Necessária para alterar e-mail ou senha." editable={!!user && !loading} />
    <ErrorNotice message={error} /><Button title="Salvar alterações" onPress={() => void save()} loading={loading} disabled={!user} />
  </FormScroll></KeyboardAvoidingView>}</Screen>;
}

export function ConnectionScreen({ navigation }: NativeStackScreenProps<RootStackParams, 'Connection'>) {
  const { endpoint, authenticated, setEndpoint } = useApp();
  const [url, setUrl] = useState(endpoint); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setBusy(true); setError(null);
    try {
      const target = normalizeNativeApiUrl(url);
      const status = await createApi(target, null, () => {}).health();
      if (status.status !== 'ready') throw new Error('O servidor ainda não está pronto. Tente novamente em instantes.');
      await setEndpoint(target); if (navigation.canGoBack()) navigation.goBack();
    } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  };
  const confirm = () => {
    if (authenticated && url.trim().replace(/\/$/, '') !== endpoint) Alert.alert('Alterar servidor?', 'Ao trocar de servidor você precisará entrar novamente.', [{ text: 'Cancelar', style: 'cancel' }, { text: 'Continuar', onPress: () => void save() }]);
    else void save();
  };
  return <Screen><Header title="Conexão" back /><FormScroll>
    <EmptyState icon="access-point-network" title="Conecte ao seu Hunter" message="Use o endereço da API que já atende sua conta Hunter." />
    <Field label="Endereço da API" value={url} onChangeText={setUrl} keyboardType="url" autoCapitalize="none" autoCorrect={false}
      placeholder="https://api.seu-hunter.com" hint={ALLOW_LOCAL_HTTP ? 'Emulador Android: http://10.0.2.2:18088. No celular, use o endereço acessível pela rede ou o encaminhamento USB.' : 'O servidor deve usar uma conexão HTTPS.'} editable={!busy} />
    <ErrorNotice message={error} /><Button title="Verificar e salvar conexão" icon="check-network-outline" onPress={confirm} loading={busy} />
    <Text style={styles.small}>As credenciais do banco não são necessárias. Use apenas o endereço da API, sem usuário ou senha na URL.</Text>
  </FormScroll></Screen>;
}
