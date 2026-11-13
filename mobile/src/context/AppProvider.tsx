import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { ApiError, createApi, type HunterApi } from '../api/client';
import type { User } from '../api/types';
import { ALLOW_LOCAL_HTTP, normalizeNativeApiUrl } from '../lib/config';

const KEY = 'hunter.mobile.session.v1';
type Session = { endpoint: string; token: string | null };
type AppContextValue = {
  api: HunterApi; endpoint: string; authenticated: boolean; user: User | null;
  ready: boolean; authError: string | null; notice: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>; updateProfile: (body: Parameters<HunterApi['updateProfile']>[0]) => Promise<void>;
  setEndpoint: (value: string) => Promise<void>; refreshUser: () => Promise<void>;
  dismissNotice: () => void;
};
const Context = createContext<AppContextValue | null>(null);
function initialEndpoint() {
  const configured = process.env.EXPO_PUBLIC_API_URL;
  const fallback = Platform.OS === 'android' ? 'http://10.0.2.2:18088' : 'http://127.0.0.1:18088';
  try { return normalizeNativeApiUrl(configured || (ALLOW_LOCAL_HTTP ? fallback : '')); }
  catch { return ''; }
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session>({ endpoint: initialEndpoint(), token: null });
  const current = useRef(session);
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const writes = useRef<Promise<void>>(Promise.resolve());
  const writeStored = useCallback((next: Session) => {
    const operation = writes.current.catch(() => {}).then(() => SecureStore.setItemAsync(KEY, JSON.stringify(next)));
    writes.current = operation;
    return operation;
  }, []);

  const persist = useCallback(async (next: Session) => {
    const previous = current.current;
    current.current = next;
    try { await writeStored(next); }
    catch {
      if (current.current === next) current.current = previous;
      throw new Error('Não foi possível salvar a sessão com segurança neste aparelho.');
    }
    if (current.current === next) { setUser(null); setAuthError(null); setSession(next); }
  }, [writeStored]);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const raw = await SecureStore.getItemAsync(KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as Session;
          const next = { endpoint: normalizeNativeApiUrl(parsed.endpoint), token: typeof parsed.token === 'string' ? parsed.token : null };
          if (active) { current.current = next; setSession(next); }
        }
      } catch {
        if (active) setNotice('Confira a conexão com o servidor e entre novamente na sua conta.');
      } finally { if (active) setReady(true); }
    })();
    return () => { active = false; };
  }, []);

  const api = useMemo(() => createApi(session.endpoint, session.token, () => {
    // Uma resposta antiga não pode encerrar uma sessão criada depois dela.
    if (current.current.token !== session.token || current.current.endpoint !== session.endpoint) return;
    const next = { ...session, token: null };
    current.current = next;
    setSession(next);
    setUser(null);
    setNotice('Sua sessão expirou. Entre novamente para ver seus alertas.');
    void writeStored(next).catch(() => {
      if (current.current === next) setNotice('A sessão expirou. Não foi possível atualizar o armazenamento seguro.');
    });
  }), [session, writeStored]);

  const refreshUser = useCallback(async () => {
    if (!session.token) return;
    const value = await api.profile();
    if (current.current === session) { setUser(value); setAuthError(null); }
  }, [api, session]);

  useEffect(() => {
    if (!ready || !session.token) return;
    void refreshUser().catch(error => {
      if (current.current === session && !(error instanceof ApiError && error.status === 401)) setAuthError(error.message);
    });
  }, [ready, refreshUser, session]);

  const acceptToken = useCallback(async (token: string, expectedEndpoint: string) => {
    if (!token) throw new Error('O servidor não retornou uma sessão válida.');
    if (current.current.endpoint !== expectedEndpoint) throw new Error('A conexão mudou. Entre novamente no servidor selecionado.');
    await persist({ endpoint: current.current.endpoint, token });
    setNotice(null);
  }, [persist]);
  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password);
    if (current.current !== session) throw new Error('A sessão mudou. Tente entrar novamente.');
    await acceptToken(result.access_token, session.endpoint);
  }, [api, acceptToken, session]);
  const updateProfile = useCallback(async (body: Parameters<HunterApi['updateProfile']>[0]) => {
    const result = await api.updateProfile(body);
    if (current.current !== session) throw new Error('A sessão mudou. Entre novamente para conferir seus dados.');
    await acceptToken(result.access_token, session.endpoint);
  }, [api, acceptToken, session]);
  const logout = useCallback(async () => {
    await persist({ endpoint: current.current.endpoint, token: null });
    setNotice(null);
  }, [persist]);
  const setEndpoint = useCallback(async (value: string) => {
    const endpoint = normalizeNativeApiUrl(value);
    if (endpoint !== current.current.endpoint) await persist({ endpoint, token: null });
  }, [persist]);

  return <Context.Provider value={{ api, endpoint: session.endpoint, authenticated: !!session.token,
    user, ready, authError, notice, login, logout, updateProfile, setEndpoint, refreshUser,
    dismissNotice: () => setNotice(null) }}>{children}</Context.Provider>;
}

export function useApp() {
  const value = useContext(Context);
  if (!value) throw new Error('AppProvider não inicializado.');
  return value;
}
