/* Comportamento da pagina: feedback. */
(() => {
    'use strict';
    const {$, element, notify, safeNext, loginURL, token, storeToken, request, busy, confirmAction, empty, safeProductLink, currency, date, getProfile, setProfile} = window.HunterUI;
    function initFeedback() {
        let editing = null;
        $('feedback').value = sessionStorage.getItem('hunterFeedbackDraft') || '';
        const count = () => { $('messageCount').textContent = $('feedback').value.length.toLocaleString('pt-BR'); };
        count();
        $('feedback').addEventListener('input', () => { count(); if (!editing) sessionStorage.setItem('hunterFeedbackDraft', $('feedback').value); });
        function reset() {
            editing = null; $('feedbackForm').reset(); count(); $('feedbackFormTitle').textContent = 'Enviar uma mensagem';
            $('saveFeedback').textContent = 'Enviar mensagem'; $('cancelFeedback').hidden = true;
        }
        async function load() {
            $('feedbackList').setAttribute('aria-busy', 'true');
            try {
                const messages = await request('/feedbacks', {auth: true});
                const cards = messages.map(item => {
                    const card = element('article', 'list-card');
                    card.append(element('span', 'tag', 'ENVIADA EM ' + date(item.data_envio)), element('p', 'message', item.feedback));
                    const actions = element('div', 'actions');
                    const edit = element('button', 'button secondary small', 'Editar'); edit.type = 'button';
                    edit.addEventListener('click', () => {
                        editing = item.id; $('feedback').value = item.feedback; count();
                        $('feedbackFormTitle').textContent = 'Editar mensagem'; $('saveFeedback').textContent = 'Salvar alterações';
                        $('cancelFeedback').hidden = false; $('feedback').focus();
                    });
                    const remove = element('button', 'button danger small', 'Excluir'); remove.type = 'button';
                    remove.addEventListener('click', async () => {
                        if (!await confirmAction('Excluir mensagem?', 'Esta mensagem será removida do seu histórico.')) return;
                        await busy(remove, async () => {
                            const result = await request(`/feedback/${item.id}`, {method: 'DELETE', auth: true});
                            if (editing === item.id) reset(); notify(result.message); await load();
                        });
                    });
                    actions.append(edit, remove); card.append(actions); return card;
                });
                $('feedbackList').replaceChildren(...cards);
                if (!messages.length) empty($('feedbackList'), 'Vamos ouvir você', 'Suas mensagens aparecerão aqui depois do envio.');
            } catch (error) {
                const retry = element('button', 'button secondary', 'Tentar novamente'); retry.addEventListener('click', load);
                empty($('feedbackList'), 'Não foi possível carregar suas mensagens', error.message, retry);
            } finally { $('feedbackList').removeAttribute('aria-busy'); }
        }
        $('cancelFeedback').addEventListener('click', () => { reset(); $('feedback').value = sessionStorage.getItem('hunterFeedbackDraft') || ''; count(); });
        $('refreshFeedback').addEventListener('click', event => busy(event.currentTarget, load));
        $('feedbackForm').addEventListener('submit', event => {
            event.preventDefault();
            const message = $('feedback').value.trim();
            if (!message) { notify('Escreva uma mensagem antes de enviar.', 'error'); $('feedback').focus(); return; }
            busy(event.submitter, async () => {
                const wasEditing = Boolean(editing);
                const result = await request(editing ? `/feedback/${editing}` : '/feedback', {method: editing ? 'PUT' : 'POST', auth: true, body: {feedback: message}});
                if (!wasEditing) sessionStorage.removeItem('hunterFeedbackDraft');
                reset(); notify(result.message); await load();
            });
        });
        return load();
    }
    window.HunterPages.feedback = initFeedback;
})();
