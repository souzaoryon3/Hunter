/* Comportamento da pagina: login. */
(() => {
    'use strict';
    const {$, element, notify, safeNext, loginURL, token, storeToken, request, busy, confirmAction, empty, safeProductLink, currency, date, getProfile, setProfile} = window.HunterUI;
    function initLogin() {
        const next = safeNext(new URLSearchParams(location.search).get('next') || 'index.html');
        for (const button of document.querySelectorAll('[data-password]')) {
            button.addEventListener('click', () => {
                const input = $(button.dataset.password);
                const show = input.type === 'password';
                input.type = show ? 'text' : 'password';
                button.textContent = show ? 'Ocultar' : 'Mostrar';
                button.setAttribute('aria-label', show ? 'Ocultar senha' : 'Mostrar senha');
            });
        }
        async function signIn(email, password) {
            const form = new FormData();
            form.append('username', email.trim()); form.append('password', password);
            const result = await request('/login', {method: 'POST', body: form});
            storeToken(result.access_token);
            sessionStorage.setItem('hunterNotice', 'Bem-vindo! Sua conta está pronta.');
            location.href = next;
        }
        $('loginForm').addEventListener('submit', event => {
            event.preventDefault();
            busy(event.submitter, () => signIn($('loginEmail').value, $('loginSenha').value));
        });
        $('cadastroForm').addEventListener('submit', event => {
            event.preventDefault();
            busy(event.submitter, async () => {
                const email = $('cadEmail').value.trim();
                const password = $('cadSenha').value;
                await request('/cadastrar', {method: 'POST', body: {nome: $('cadNome').value.trim(), email, senha: password}});
                try { await signIn(email, password); }
                catch (error) { $('loginEmail').value = email; notify('Sua conta foi criada. Entre pelo formulário de login.', 'info'); }
            });
        });
    }
    window.HunterPages.login = initLogin;
})();
