export const currency = (value: number | string | null | undefined) =>
  value == null ? '—' : new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value));

export function date(value: string | null | undefined) {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Sem data de coleta';
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
}

export function parseMoney(value: string): number | undefined {
  let text = value.trim().replace(/^R\$\s*/, '');
  if (!text) return undefined;
  if (text.includes(',')) {
    if (!/^(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?$/.test(text)) throw new Error('Informe um valor válido, como 199,90.');
    text = text.replace(/\./g, '').replace(',', '.');
  } else if (!/^\d+(?:\.\d{1,2})?$/.test(text)) {
    throw new Error('Informe um valor válido, como 199,90.');
  }
  const amount = Number(text);
  if (!Number.isFinite(amount) || amount < 0 || amount > 1_000_000_000) throw new Error('Valor fora do intervalo permitido.');
  return amount;
}

export function safeProductUrl(value: string | null | undefined): string | null {
  try {
    const url = new URL(value ?? '');
    return url.protocol === 'https:' && !!url.hostname && !url.username && !url.password ? url.toString() : null;
  } catch { return null; }
}

export function validatePassword(value: string) {
  const bytes = Array.from(value).reduce((total, char) => {
    const code = char.codePointAt(0)!;
    return total + (code > 0xffff ? 4 : code > 0x7ff ? 3 : code > 0x7f ? 2 : 1);
  }, 0);
  if (Array.from(value).length < 8 || bytes > 72) throw new Error('Use ao menos 8 caracteres e no máximo 72 bytes na senha.');
}
