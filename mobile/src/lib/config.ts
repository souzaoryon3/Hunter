import { normalizeApiUrl } from '../api/client';

// Flag explicita somente para APKs internos que acessam a API na rede local.
export const ALLOW_LOCAL_HTTP = __DEV__ || process.env.EXPO_PUBLIC_LOCAL_PREVIEW === '1';
export const normalizeNativeApiUrl = (value: string) => normalizeApiUrl(value, ALLOW_LOCAL_HTTP, !__DEV__);
