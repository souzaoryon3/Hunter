/* Comportamento da pagina: profile. */
(() => {
    'use strict';
    const {$, element, notify, safeNext, loginURL, token, storeToken, request, busy, confirmAction, empty, safeProductLink, currency, date, getProfile, setProfile} = window.HunterUI;
    function initProfile() {
        $('updateNome').value = getProfile().nome; $('updateEmail').value = getProfile().email;
        $('updateUserForm').addEventListener('submit', event => {
            event.preventDefault();
            const data = {};
            if ($('updateNome').value.trim() !== getProfile().nome) data.nome = $('updateNome').value.trim();
            if ($('updateEmail').value.trim() !== getProfile().email) data.email = $('updateEmail').value.trim();
            if ($('updateSenha').value) data.senha = $('updateSenha').value;
            if (!Object.keys(data).length) { notify('Seus dados já estão atualizados.', 'info'); return; }
            if ((data.email || data.senha) && !$('currentPassword').value) {
                notify('Confirme sua senha atual para alterar o e-mail ou a senha.', 'error'); $('currentPassword').focus(); return;
            }
            data.senha_atual = $('currentPassword').value || undefined;
            busy(event.submitter, async () => {
                const result = await request('/usuario', {method: 'PUT', auth: true, body: data});
                storeToken(result.access_token); setProfile(await request('/usuario', {auth: true}));
                $('updateNome').value = getProfile().nome; $('updateEmail').value = getProfile().email;
                $('updateSenha').value = ''; $('currentPassword').value = ''; notify(result.message);
            });
        });
        $('deleteUserBtn').addEventListener('click', async event => {
            const button = event.currentTarget;
            if (!await confirmAction('Excluir sua conta permanentemente?', 'Sua conta, seus alertas e suas mensagens serão removidos. Esta ação não pode ser desfeita.')) return;
            busy(button, async () => {
                const result = await request('/usuario', {method: 'DELETE', auth: true});
                localStorage.removeItem('token'); sessionStorage.removeItem('hunterFeedbackDraft');
                sessionStorage.setItem('hunterNotice', result.message); location.href = 'index.html';
            });
        });
    }
    window.HunterPages.profile = initProfile;
})();
