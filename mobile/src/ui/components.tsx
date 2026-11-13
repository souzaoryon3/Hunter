import React, { useState } from 'react';
import { ActivityIndicator, Image, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
  type TextInputProps, type ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParams } from '../navigation/types';
import type { Product } from '../api/types';
import { safeProductUrl, currency } from '../lib/format';
import { colors, styles } from './theme';

export type IconName = React.ComponentProps<typeof MaterialCommunityIcons>['name'];
export function Icon({ name, size = 22, color = colors.ink }: { name: IconName; size?: number; color?: string }) {
  return <MaterialCommunityIcons name={name} size={size} color={color} />;
}
export function Screen({ children }: { children: React.ReactNode }) {
  return <SafeAreaView style={styles.page} edges={['top', 'left', 'right']}>{children}</SafeAreaView>;
}
export function FormScroll({ children }: { children: React.ReactNode }) {
  return <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>{children}</ScrollView>;
}
export function Header({ title, subtitle, back = false, right }: { title: string; subtitle?: string; back?: boolean; right?: React.ReactNode }) {
  const navigation = useNavigation();
  return <View style={{ paddingHorizontal: 20, paddingTop: 12, paddingBottom: 18, gap: 6 }}>
    <View style={styles.between}>
      <View style={[styles.row, { flex: 1 }]}>
        {back && <Pressable accessibilityRole="button" accessibilityLabel="Voltar" onPress={() => navigation.goBack()} style={local.iconButton}><Icon name="arrow-left" /></Pressable>}
        <Text style={[styles.title, { fontSize: back ? 23 : 29, flexShrink: 1 }]}>{title}</Text>
      </View>{right}
    </View>
    {!!subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
  </View>;
}
export function Button({ title, onPress, loading = false, disabled = false, secondary = false, danger = false, icon, style }: {
  title: string; onPress: () => void; loading?: boolean; disabled?: boolean; secondary?: boolean;
  danger?: boolean; icon?: IconName; style?: ViewStyle;
}) {
  const textColor = danger ? colors.danger : secondary ? colors.ink : colors.white;
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled: disabled || loading, busy: loading }}
    disabled={disabled || loading} onPress={onPress}
    style={({ pressed }) => [local.button, { backgroundColor: danger ? colors.dangerBg : secondary ? colors.lime : colors.green,
      opacity: disabled || loading ? .55 : pressed ? .8 : 1 }, style]}>
    {loading ? <ActivityIndicator color={textColor} /> : <>{icon && <Icon name={icon} color={textColor} size={19} />}<Text style={[local.buttonText, { color: textColor }]}>{title}</Text></>}
  </Pressable>;
}
export function Field({ label, hint, ...props }: TextInputProps & { label: string; hint?: string }) {
  return <View style={{ gap: 7 }}>
    <Text style={{ color: colors.ink, fontSize: 13, fontWeight: '600' }}>{label}</Text>
    <TextInput accessibilityLabel={label} placeholderTextColor={colors.muted} {...props}
      style={[local.input, props.multiline && { minHeight: 100, textAlignVertical: 'top' }, props.style]} />
    {hint && <Text style={styles.small}>{hint}</Text>}
  </View>;
}
export function ErrorNotice({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  if (!message) return null;
  return <View accessibilityLiveRegion="polite" style={{ padding: 14, borderRadius: 14, backgroundColor: colors.dangerBg, gap: 10 }}>
    <Text style={{ color: colors.danger, fontSize: 14, lineHeight: 21 }}>{message}</Text>
    {onRetry && <Pressable accessibilityRole="button" onPress={onRetry} style={{ minHeight: 36, justifyContent: 'center' }}><Text style={{ color: colors.danger, fontWeight: '700' }}>Tentar novamente</Text></Pressable>}
  </View>;
}
export function EmptyState({ icon = 'radar', title, message, loading, action }: { icon?: IconName; title: string; message?: string; loading?: boolean; action?: React.ReactNode }) {
  return <View style={{ padding: 26, alignItems: 'center', gap: 14 }}>
    <View style={{ width: 64, height: 64, borderRadius: 22, backgroundColor: colors.pale, alignItems: 'center', justifyContent: 'center' }}>
      {loading ? <ActivityIndicator color={colors.green} /> : <Icon name={icon} color={colors.green} size={30} />}
    </View>
    <Text style={[styles.section, { textAlign: 'center' }]}>{title}</Text>
    {message && <Text style={[styles.subtitle, { textAlign: 'center' }]}>{message}</Text>}
    {action}
  </View>;
}
export function Guest({ title = 'Sua próxima boa compra começa aqui.', message = 'Entre para acompanhar seus alertas e receber as novidades das suas ofertas.' }: { title?: string; message?: string }) {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  return <EmptyState icon="account-key-outline" title={title} message={message}
    action={<Button title="Entrar ou criar conta" onPress={() => navigation.navigate('Auth')} />} />;
}
export function ProductImage({ uri, large = false }: { uri: string | null; large?: boolean }) {
  const [failed, setFailed] = useState(false);
  const source = safeProductUrl(uri);
  return <View style={{ height: large ? 240 : 122, backgroundColor: colors.white, borderRadius: 14, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
    {source && !failed ? <Image source={{ uri: source }} resizeMode="contain" onError={() => setFailed(true)} style={{ width: '90%', height: '90%' }} accessibilityLabel="Imagem do produto" /> : <Icon name="devices" size={large ? 64 : 40} color={colors.muted} />}
  </View>;
}
export function ProductCard({ product }: { product: Product }) {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParams>>();
  return <Pressable accessibilityRole="button" accessibilityLabel={`${product.nome}, ${currency(product.preco)}, ${product.loja}`}
    onPress={() => navigation.navigate('Product', { product })} style={({ pressed }) => [styles.card, { flex: 1, padding: 12, gap: 9, opacity: pressed ? .8 : 1 }]}>
    <ProductImage key={product.imagem_url} uri={product.imagem_url} />
    <View style={styles.badge}><Text style={styles.badgeText}>{product.loja}</Text></View>
    <Text numberOfLines={3} style={{ color: colors.ink, fontWeight: '600', fontSize: 13, lineHeight: 19, minHeight: 57 }}>{product.nome}</Text>
    <Text style={{ color: colors.ink, fontSize: 21, fontWeight: '800', letterSpacing: -.6 }}>{currency(product.preco)}</Text>
    <Text style={styles.small}>{product.frete_gratis ? 'Frete grátis anunciado' : 'Confira as condições'}</Text>
  </Pressable>;
}
export async function openProduct(value: string | null | undefined) {
  const url = safeProductUrl(value);
  if (!url) throw new Error('O endereço desta oferta não é válido.');
  try { await Linking.openURL(url); }
  catch { throw new Error('Não foi possível abrir a loja neste aparelho.'); }
}
export function ActionRow({ icon, title, subtitle, onPress }: { icon: IconName; title: string; subtitle?: string; onPress: () => void }) {
  return <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.row, { paddingVertical: 16, opacity: pressed ? .6 : 1, minHeight: 52 }]}>
    <Icon name={icon} color={colors.green} /><View style={{ flex: 1, gap: 2 }}><Text style={[styles.body, { fontWeight: '600' }]}>{title}</Text>{subtitle && <Text style={styles.small}>{subtitle}</Text>}</View><Icon name="chevron-right" size={19} color={colors.muted} />
  </Pressable>;
}
const local = StyleSheet.create({
  iconButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.white, alignItems: 'center', justifyContent: 'center' },
  button: { minHeight: 50, borderRadius: 15, paddingVertical: 14, paddingHorizontal: 19, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 9 },
  buttonText: { fontSize: 14, fontWeight: '700' },
  input: { minHeight: 52, backgroundColor: colors.white, borderRadius: 14, borderWidth: 1, borderColor: colors.line, paddingHorizontal: 14, paddingVertical: 13, color: colors.ink, fontSize: 16 },
});
