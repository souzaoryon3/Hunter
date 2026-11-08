/* Transporte HTTP e sessao; nenhuma credencial incorporada. */
(() => {
    'use strict';
    const apiBase = window.HUNTER_API_URL || (['localhost', '127.0.0.1'].includes(location.hostname)
        ? `${location.protocol}//${location.hostname}:8000` : location.origin);
    function expireSession() { window.HunterAPI.onExpired?.(); }
    function tokenData(token) {
        try {
            const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
            const payload = JSON.parse(atob(part));
            return typeof payload.exp === 'number' && typeof payload.sub === 'string' ? payload : null;
        } catch { return null; }
    }

    function token() {
        const value = localStorage.getItem('token');
        const data = value && tokenData(value);
        return data && data.exp * 1000 > Date.now() ? value : null;
    }

    async function request(path, {method = 'GET', body, auth = false, signal} = {}) {
        const headers = {};
        if (auth) {
            const value = token();
            if (!value) { expireSession(); throw new Error('Entre novamente para continuar.'); }
            headers.Authorization = `Bearer ${value}`;
        }
        if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
        const controller = new AbortController();
        const abort = () => controller.abort();
        if (signal?.aborted) controller.abort();
        signal?.addEventListener('abort', abort, {once: true});
        const timeout = setTimeout(abort, 20000);
        try {
            const response = await fetch(apiBase + path, {
                method, headers, body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body), signal: controller.signal,
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                if (response.status === 401 && auth) expireSession();
                const detail = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail)
                    ? data.detail.map(item => item.msg.replace(/^Value error, /, '')).join(' ') : 'Não foi possível concluir. Tente novamente.';
                throw new Error(detail);
            }
            return data;
        } catch (error) {
            if (signal?.aborted) throw error;
            if (error.name === 'AbortError') throw new Error('A consulta demorou mais que o esperado. Tente novamente.');
            if (error instanceof TypeError) throw new Error('Não foi possível conectar ao Hunter. Verifique sua conexão e tente novamente.');
            throw error;
        } finally {
            clearTimeout(timeout);
            signal?.removeEventListener('abort', abort);
        }
    }
    window.HunterAPI = {apiBase, tokenData, token, request, onExpired: null};
})();
