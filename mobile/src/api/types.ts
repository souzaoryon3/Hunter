export type Money = number | string;
export type User = { id: number; nome: string; email: string };
export type Product = {
  produto_id: number | null;
  nome: string;
  loja: string;
  link: string;
  imagem_url: string | null;
  preco: Money;
  preco_cartao: Money | null;
  pagamento: string | null;
  coletado_em: string | null;
  historico_disponivel: boolean;
  frete_gratis: boolean | null;
  frete_observacao: string | null;
  price_kind?: 'regular' | 'promotional';
  promotion_terms?: string | null;
};
export type SearchFilters = {
  query: string;
  store?: string;
  min?: number;
  max?: number;
  order?: 'priceAsc' | 'priceDesc';
  freeShipping?: boolean;
};
export type SearchResult = { produtos: Product[]; total: number; pagina: number; limite: number };
export type Observation = {
  id: number; nome: string; preco: Money; preco_cartao: Money | null;
  coletado_em: string; pagamento: string | null; disponivel: boolean;
};
export type HistoryResult = {
  produto: { id: number; loja: string; link: string };
  historico: Observation[]; total: number; pagina: number; limite: number;
};
export type PriceAlert = {
  id: number; produto: string; preco: Money; preco_atual: Money | null;
  loja: string | null; link: string | null; atingido: boolean; data: string;
};
export type Notification = {
  id: number; produto: string; preco: Money; preco_desejado: Money;
  loja: string; link: string; created_at: string; read_at: string | null;
};
export type NotificationResult = {
  notificacoes: Notification[]; total: number; nao_lidas: number; pagina: number; limite: number;
};
