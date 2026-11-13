import { StyleSheet } from 'react-native';
export const colors = {
  ink: '#18231d', muted: '#667267', paper: '#f5f6f0', white: '#ffffff',
  line: '#e1e6dc', lime: '#e4fa66', green: '#285a3e', pale: '#eaf1e6',
  danger: '#a53030', dangerBg: '#fff0ed',
};
export const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.paper },
  content: { padding: 20, gap: 16, paddingBottom: 32 },
  title: { fontSize: 30, fontWeight: '800', color: colors.ink, letterSpacing: -1 },
  subtitle: { fontSize: 15, color: colors.muted, lineHeight: 23 },
  section: { fontSize: 20, fontWeight: '700', color: colors.ink, letterSpacing: -.4 },
  body: { fontSize: 15, color: colors.ink, lineHeight: 23 },
  small: { fontSize: 12, color: colors.muted, lineHeight: 19 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  between: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  card: { backgroundColor: colors.white, padding: 18, borderRadius: 20, borderWidth: 1, borderColor: colors.line, gap: 12 },
  chip: { paddingHorizontal: 15, paddingVertical: 10, borderRadius: 30, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.white, minHeight: 42, justifyContent: 'center' },
  chipActive: { backgroundColor: colors.ink, borderColor: colors.ink },
  chipText: { color: colors.ink, fontSize: 13, fontWeight: '600' },
  badge: { backgroundColor: colors.pale, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, alignSelf: 'flex-start' },
  badgeText: { color: colors.green, fontSize: 11, fontWeight: '700' },
  divider: { height: 1, backgroundColor: colors.line },
});
