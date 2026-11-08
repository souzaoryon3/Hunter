/* Comportamento da pagina: alerts. */
(() => {
    'use strict';
    const {$, element, notify, safeNext, loginURL, token, storeToken, request, busy, confirmAction, empty, safeProductLink, currency, date, getProfile, setProfile} = window.HunterUI;
    function initAlerts() {
        let editing = null;
        let notificationPage = 1, notificationShown = 0, notificationLoading = false;
        async function loadNotifications(append = false) {
            if (notificationLoading || !$('notificationList') || !token()) return;
            notificationLoading = true;
            $('notificationList').setAttribute('aria-busy', 'true');
            try {
                const data = await request('/notificacoes?' + new URLSearchParams({pagina: append ? notificationPage + 1 : 1, limite: 20}), {auth: true});
                const items = data.notificacoes || [];
                if (!append) { $('notificationList').replaceChildren(); notificationShown = 0; }
                notificationPage = data.pagina || 1;
                for (const item of items) {
                    const card = element('article', 'list-card');
                    card.append(element('span', 'status' + (item.read_at ? '' : ' reached'), item.read_at ? 'Lida' : 'Nova oferta'),
                        element('h3', '', item.produto), element('p', 'product-price', currency(item.preco)),
                        element('p', 'hint', `${item.loja} · Preço desejado: ${currency(item.preco_desejado)} · ${date(item.created_at)}`));
                    const actions = element('div', 'actions');
                    const href = safeProductLink(item.link);
                    if (href) {
                        const offer = element('a', 'button primary small', 'Ver oferta ↗');
                        offer.href = href; offer.target = '_blank'; offer.rel = 'noopener noreferrer'; actions.append(offer);
                    }
                    if (!item.read_at) {
                        const read = element('button', 'button secondary small', 'Marcar como lida'); read.type = 'button';
                        read.addEventListener('click', () => busy(read, async () => {
                            await request(`/notificacoes/${item.id}/lida`, {method: 'PUT', auth: true});
                            await loadNotifications();
                        }));
                        actions.append(read);
                    }
                    card.append(actions); $('notificationList').append(card);
                }
                notificationShown += items.length;
                $('unreadCount').textContent = `${data.nao_lidas || 0} não lidas`;
                $('moreNotifications').hidden = notificationShown >= (data.total || 0);
                if (!notificationShown) empty($('notificationList'), 'Nenhuma notificação ainda', 'Seus avisos de preço aparecerão aqui após o processamento dos alertas.');
            } catch (error) {
                const retry = element('button', 'button secondary', 'Tentar novamente');
                retry.type = 'button'; retry.addEventListener('click', () => loadNotifications());
                if (!append) empty($('notificationList'), 'Não foi possível carregar as notificações', error.message, retry);
                else notify(error.message, 'error');
            } finally { notificationLoading = false; $('notificationList').removeAttribute('aria-busy'); }
        }
        $('refreshNotifications')?.addEventListener('click', () => loadNotifications());
        $('moreNotifications')?.addEventListener('click', () => loadNotifications(true));
        // Atualiza somente enquanto esta página autenticada estiver visível.
        const notificationTimer = setInterval(() => {
            if (!document.hidden && token() && notificationPage === 1) loadNotifications();
        }, 30000);
        window.addEventListener('pagehide', () => clearInterval(notificationTimer), {once: true});
        const params = new URLSearchParams(location.search);
        if (params.get('produto')) $('produto').value = params.get('produto').slice(0, 255);
        if (params.get('preco')) $('preco').value = params.get('preco');
        function reset() {
            editing = null; $('alertForm').reset(); $('alertFormTitle').textContent = 'Criar alerta';
            $('saveAlert').textContent = 'Salvar alerta'; $('cancelAlert').hidden = true;
            history.replaceState(null, '', 'alertas.html');
        }
        async function load() {
            $('alertsList').setAttribute('aria-busy', 'true');
            try {
                const alerts = await request('/alertas', {auth: true});
                const cards = alerts.map(item => {
                    const card = element('article', 'list-card');
                    card.append(element('span', `status${item.atingido ? ' reached' : ''}`, item.atingido ? 'Preço alvo encontrado' : item.preco_atual == null ? 'Sem oferta no catálogo' : 'Acompanhando'), element('h3', '', item.produto));
                    const prices = element('div', 'price-row');
                    const target = element('div'); target.append(element('span', 'subtle', 'Seu preço desejado'), element('strong', '', currency(item.preco)));
                    const current = element('div'); current.append(element('span', 'subtle', 'Menor preço no catálogo'), element('strong', '', item.preco_atual == null ? 'Não encontrado' : currency(item.preco_atual)));
                    prices.append(target, current); card.append(prices, element('p', 'hint', 'Criado em ' + date(item.data)));
                    const actions = element('div', 'actions');
                    const edit = element('button', 'button secondary small', 'Editar'); edit.type = 'button';
                    edit.addEventListener('click', () => {
                        editing = item.id; $('produto').value = item.produto; $('preco').value = Number(item.preco).toFixed(2);
                        $('alertFormTitle').textContent = 'Editar alerta'; $('saveAlert').textContent = 'Salvar alterações';
                        $('cancelAlert').hidden = false; $('produto').focus();
                    });
                    const remove = element('button', 'button danger small', 'Excluir'); remove.type = 'button';
                    remove.addEventListener('click', async () => {
                        if (!await confirmAction('Excluir alerta?', 'Você poderá criar um novo alerta para este produto quando quiser.')) return;
                        await busy(remove, async () => {
                            const result = await request(`/alerta/${item.id}`, {method: 'DELETE', auth: true});
                            if (editing === item.id) reset(); notify(result.message); await load();
                        });
                    });
                    actions.append(edit, remove);
                    if (safeProductLink(item.link)) {
                        const offer = element('a', 'button secondary small', 'Ver oferta ↗');
                        offer.href = safeProductLink(item.link); offer.target = '_blank'; offer.rel = 'noopener noreferrer'; actions.append(offer);
                    }
                    card.append(actions); return card;
                });
                $('alertsList').replaceChildren(...cards);
                if (!alerts.length) empty($('alertsList'), 'Seu primeiro alerta está a um passo', 'Cadastre um produto e um preço desejado ou escolha uma oferta na busca.');
            } catch (error) {
                const retry = element('button', 'button secondary', 'Tentar novamente'); retry.addEventListener('click', load);
                empty($('alertsList'), 'Não foi possível carregar seus alertas', error.message, retry);
            } finally { $('alertsList').removeAttribute('aria-busy'); }
        }
        $('cancelAlert').addEventListener('click', reset);
        $('refreshAlerts').addEventListener('click', event => busy(event.currentTarget, load));
        $('alertForm').addEventListener('submit', event => {
            event.preventDefault();
            busy(event.submitter, async () => {
                const result = await request(editing ? `/alerta/${editing}` : '/alerta-preco', {method: editing ? 'PUT' : 'POST', auth: true,
                    body: {produto: $('produto').value.trim(), preco: Number($('preco').value)}});
                reset(); notify(result.message); await load();
            });
        });
        return Promise.all([load(), loadNotifications()]);
    }
    window.HunterPages.alerts = initAlerts;
})();
