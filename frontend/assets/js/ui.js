/* Interface compartilhada do Hunter. Sem dependência de framework. */
(() => {
    'use strict';
    const $ = id => document.getElementById(id);
    const page = document.body.dataset.page;
    const safePages = ['index.html', 'buscar.html', 'alertas.html', 'feedback.html', 'configurar.html', 'dashboard.html'];
    if (!$('navLinks').querySelector('a[href="dashboard.html"]')) {
        const analyticsLink = document.createElement('a');
        analyticsLink.href = 'dashboard.html'; analyticsLink.textContent = 'Análises';
        if (page === 'analytics') analyticsLink.setAttribute('aria-current', 'page');
        $('navLinks').insertBefore(analyticsLink, $('loginNav'));
    }
    const {tokenData, token, request} = window.HunterAPI;
    window.HunterAPI.onExpired = expireSession;
    let sessionTimer;
    let profile = null;

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function notify(message, type = 'success') {
        const box = element('div', `notice ${type}`);
        box.setAttribute('role', type === 'error' ? 'alert' : 'status');
        box.append(element('span', '', message));
        const close = element('button', '', '×');
        close.type = 'button';
        close.setAttribute('aria-label', 'Fechar mensagem');
        close.addEventListener('click', () => box.remove());
        box.append(close);
        $('notifications').replaceChildren(box);
    }

    function safeNext(value) {
        try {
            const url = new URL(value, location.href);
            const filename = url.pathname.split('/').pop();
            return url.origin === location.origin && safePages.includes(filename)
                ? filename + url.search : 'index.html';
        } catch { return 'index.html'; }
    }

    function loginURL(next = location.pathname.split('/').pop() + location.search) {
        return `login.html?next=${encodeURIComponent(safeNext(next))}`;
    }





    function updateNavigation() {
        const logged = Boolean(token());
        $('loginNav').hidden = logged;
        $('logoutLink').hidden = !logged;
        for (const link of document.querySelectorAll('.nav-links a')) {
            if (link.getAttribute('href') === location.pathname.split('/').pop() ||
                (location.pathname.endsWith('/') && link.getAttribute('href') === 'index.html')) {
                link.setAttribute('aria-current', 'page');
            }
        }
    }

    function gate(message = 'Entre na sua conta para continuar.') {
        if (!$('authGate')) return;
        $('protectedContent').hidden = true;
        const box = element('section', 'empty-state');
        box.append(element('span', 'empty-icon', '◎'), element('h2', '', 'Seu espaço no Hunter'), element('p', '', message));
        const link = element('a', 'button primary', 'Entrar / Criar conta');
        link.href = loginURL();
        box.append(link);
        $('authGate').replaceChildren(box);
    }

    function expireSession() {
        localStorage.removeItem('token');
        profile = null;
        clearTimeout(sessionTimer);
        updateNavigation();
        gate('Sua sessão expirou. Entre novamente para continuar.');
        notify('Sua sessão expirou. Faça login novamente para continuar.', 'info');
    }

    function storeToken(value) {
        localStorage.setItem('token', value);
        scheduleSession();
        updateNavigation();
    }

    function scheduleSession() {
        clearTimeout(sessionTimer);
        const value = token();
        if (!value) return;
        const remaining = tokenData(value).exp * 1000 - Date.now();
        sessionTimer = setTimeout(expireSession, Math.min(remaining + 100, 2147483647));
    }



    async function busy(button, action) {
        if (button.disabled) return;
        const original = button.textContent;
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
        const spinner = element('span', 'spinner');
        spinner.setAttribute('aria-hidden', 'true');
        button.replaceChildren(spinner, document.createTextNode(' Aguarde...'));
        try { return await action(); }
        catch (error) { notify(error.message, 'error'); }
        finally {
            button.disabled = false;
            button.removeAttribute('aria-busy');
            if (button.querySelector('.spinner')) button.textContent = original;
        }
    }

    function confirmAction(title, text) {
        return new Promise(resolve => {
            const dialog = $('confirmDialog');
            $('confirmTitle').textContent = title;
            $('confirmText').textContent = text;
            dialog.returnValue = 'cancel';
            dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), {once: true});
            dialog.showModal();
            dialog.querySelector('[value="cancel"]').focus();
        });
    }

    function empty(target, title, description, action) {
        const box = element('div', 'empty-state');
        box.append(element('span', 'empty-icon', '◎'), element('h3', '', title), element('p', '', description));
        if (action) box.append(action);
        target.replaceChildren(box);
    }

    function safeProductLink(link) {
        try {
            const url = new URL(link);
            return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
        } catch { return null; }
    }

    const currency = value => Number(value).toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
    const date = value => value ? new Date(value).toLocaleDateString('pt-BR') : 'Data não informada';

    $('menuToggle').addEventListener('click', () => {
        const opened = $('navLinks').classList.toggle('open');
        $('menuToggle').setAttribute('aria-expanded', String(opened));
    });
    $('logoutLink').addEventListener('click', () => {
        localStorage.removeItem('token');
        sessionStorage.removeItem('hunterFeedbackDraft');
        clearTimeout(sessionTimer);
        sessionStorage.setItem('hunterNotice', 'Você saiu da sua conta. Até a próxima!');
        location.href = 'index.html';
    });
    window.addEventListener('storage', event => {
        if (event.key === 'token') {
            if (!token()) expireSession();
            else { scheduleSession(); updateNavigation(); location.reload(); }
        }
    });
    if (localStorage.getItem('token') && !token()) {
        localStorage.removeItem('token');
        notify('Sua sessão expirou. Entre novamente quando quiser salvar ou gerenciar seus produtos.', 'info');
    }
    updateNavigation();
    scheduleSession();
    const flash = sessionStorage.getItem('hunterNotice');
    if (flash) { sessionStorage.removeItem('hunterNotice'); notify(flash); }
    window.addEventListener('load', () => {
        if (window.VLibras) new window.VLibras.Widget('https://vlibras.gov.br/app');
    });

    async function protectedPage(init) {
        if (!token()) { gate(); return; }
        try {
            profile = await request('/usuario', {auth: true});
            $('protectedContent').hidden = false;
            $('authGate').replaceChildren();
            await init();
        } catch (error) {
            if (token()) {
                const retry = element('button', 'button secondary', 'Tentar novamente');
                retry.type = 'button';
                retry.addEventListener('click', () => protectedPage(init));
                empty($('authGate'), 'Não conseguimos carregar sua conta', error.message, retry);
            }
        }
    }













    window.HunterUI = {$, element, notify, safeNext, loginURL, token, storeToken, request, busy, confirmAction, empty, safeProductLink, currency, date, getProfile: () => profile, setProfile: value => { profile = value; }};
    window.HunterPages = {};
    document.addEventListener('DOMContentLoaded', () => {
        const init = window.HunterPages[page];
        if (!init) return;
        if (['alerts', 'feedback', 'profile'].includes(page)) protectedPage(init);
        else init();
    });
})();
