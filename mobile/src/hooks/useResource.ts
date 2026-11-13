import { useCallback, useEffect, useRef, useState, type SetStateAction } from 'react';
import { useFocusEffect } from '@react-navigation/native';

export function useResource<T>(load: () => Promise<T>, enabled = true) {
  const [stored, setStored] = useState<{ scope: typeof load; value: T | null }>({ scope: load, value: null });
  const data = stored.scope === load ? stored.value : null;
  const setData = useCallback((next: SetStateAction<T | null>) => {
    setStored(previous => {
      const value = previous.scope === load ? previous.value : null;
      return { scope: load, value: typeof next === 'function' ? (next as (value: T | null) => T | null)(value) : next };
    });
  }, [load]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  useEffect(() => { setData(null); setError(null); }, [setData]);
  const refresh = useCallback(async () => {
    if (!enabled) return;
    const id = ++generation.current;
    setLoading(true); setError(null);
    try { const result = await load(); if (id === generation.current) setData(result); }
    catch (err) { if (id === generation.current) setError(err instanceof Error ? err.message : 'Não foi possível carregar os dados.'); }
    finally { if (id === generation.current) setLoading(false); }
  }, [load, enabled, setData]);
  useFocusEffect(useCallback(() => {
    if (enabled) void refresh();
    else { setData(null); setError(null); setLoading(false); }
    return () => { generation.current += 1; };
  }, [enabled, refresh, setData]));
  return { data, setData, loading, error: stored.scope === load ? error : null, refresh };
}
