import type { User, SearchFilters, SearchResult, HistoryResult, PriceAlert, NotificationResult } from './types';

export class ApiError extends Error {
  constructor(message: string, public status = 0) { super(message); this.name = 'ApiError'; }
}

export function normalizeApiUrl(value: string, allowHttp: boolean, privateHttpOnly = false): string {
  try {
    const url = new URL(value.trim());
    if (url.username || url.password || url.search || url.hash || (url.pathname !== '/' && url.pathname !== '')) throw new Error();
    if (!url.hostname || (url.protocol !== 'https:' && !(allowHttp && url.protocol === 'http:'))) throw new Error();
    if (url.protocol === 'http:' && privateHttpOnly) {
      const parts = url.hostname.split('.').map(Number);
      const privateV4 = parts.length === 4 && parts.every(part => Number.isInteger(part) && part >= 0 && part <= 255)
        && (parts[0] === 10 || parts[0] === 127 || (parts[0] === 192 && parts[1] === 168)
          || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31));
      if (!privateV4 && url.hostname !== 'localhost' && url.hostname !== '[::1]') throw new Error();
    }
    return url.origin;
  } catch { throw new ApiError(allowHttp ? 'Informe a URL da API, como http://10.0.2.2:18088.' : 'Use uma URL HTTPS válida para a API.'); }
}

function detailMessage(data: unknown): string | undefined {
  if (!data || typeof data !== 'object' || !('detail' in data)) return;
  const detail = data.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item?.msg).filter(Boolean).join('\n');
}

type RequestOptions = { method?: string; body?: object | URLSearchParams; authenticated?: boolean; signal?: AbortSignal };

export function createApi(baseUrl: string, token: string | null, onExpired: () => void, transport: typeof fetch = fetch) {
  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    if (!baseUrl) throw new ApiError('Configure o endereço da API em Conta → Conexão.');
    if (!path.startsWith('/') || path.startsWith('//')) throw new ApiError('Caminho de API inválido.');
    if (options.authenticated && !token) throw new ApiError('Entre na sua conta para continuar.', 401);
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (options.signal?.aborted) abort();
    options.signal?.addEventListener('abort', abort);
    const timer = setTimeout(abort, 15_000);
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (options.authenticated && token) headers.Authorization = `Bearer ${token}`;
    let body: string | undefined;
    if (options.body instanceof URLSearchParams) {
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
      body = options.body.toString();
    } else if (options.body) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(options.body);
    }
    try {
      const response = await transport(baseUrl + path, { method: options.method ?? 'GET', headers, body, signal: controller.signal, redirect: 'error' });
      if (response.status === 401 && options.authenticated) {
        onExpired();
        throw new ApiError('Sua sessão expirou. Entre novamente.', 401);
      }
      const text = await response.text();
      let data: unknown;
      try { data = text ? JSON.parse(text) : null; }
      catch { throw new ApiError('O servidor não retornou uma resposta válida. Confira o endereço da API.', response.status); }
      if (!response.ok) {
        throw new ApiError(detailMessage(data) || `Não foi possível concluir a operação (${response.status}).`, response.status);
      }
      return data as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (options.signal?.aborted) throw error;
      throw new ApiError(controller.signal.aborted ? 'A conexão demorou demais. Tente novamente.' : 'Não foi possível conectar ao Hunter. Confira a conexão e o endereço da API em Conta.');
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', abort);
    }
  }
  return {
    health: () => request<{ status: string }>('/health/ready'),
    shops: () => request<{ lojas: string[] }>('/lojas'),
    search: (filters: SearchFilters, page = 1, signal?: AbortSignal) => {
      const params = new URLSearchParams({ nome: filters.query.trim(), pagina: String(page), limite: '20', ordem: filters.order ?? 'priceAsc' });
      if (filters.store) params.set('loja', filters.store);
      if (filters.min != null) params.set('preco_min', String(filters.min));
      if (filters.max != null) params.set('preco_max', String(filters.max));
      if (filters.freeShipping) params.set('frete_gratis', 'true');
      return request<SearchResult>(`/buscar-produtos?${params}`, { signal });
    },
    history: (id: number, page = 1) => request<HistoryResult>(`/produtos/${id}/historico?pagina=${page}&limite=20`),
    login: (email: string, password: string) => request<{ access_token: string }>('/login', { method: 'POST', body: new URLSearchParams({ username: email.trim(), password }) }),
    register: (nome: string, email: string, senha: string) => request<{ usuario_id: number }>('/cadastrar', { method: 'POST', body: { nome: nome.trim(), email: email.trim(), senha } }),
    profile: () => request<User>('/usuario', { authenticated: true }),
    updateProfile: (body: { nome?: string; email?: string; senha?: string; senha_atual?: string }) => request<{ access_token: string }>('/usuario', { method: 'PUT', body, authenticated: true }),
    alerts: () => request<PriceAlert[]>('/alertas', { authenticated: true }),
    createAlert: (produto: string, preco: number) => request<{ id: number }>('/alerta-preco', { method: 'POST', body: { produto: produto.trim(), preco }, authenticated: true }),
    updateAlert: (id: number, produto: string, preco: number) => request<{ message: string }>(`/alerta/${id}`, { method: 'PUT', body: { produto: produto.trim(), preco }, authenticated: true }),
    deleteAlert: (id: number) => request<{ message: string }>(`/alerta/${id}`, { method: 'DELETE', authenticated: true }),
    notifications: (page = 1) => request<NotificationResult>(`/notificacoes?pagina=${page}&limite=20`, { authenticated: true }),
    readNotification: (id: number) => request<{ message: string }>(`/notificacoes/${id}/lida`, { method: 'PUT', authenticated: true }),
  };
}
export type HunterApi = ReturnType<typeof createApi>;
