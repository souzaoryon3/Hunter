/* Comportamento da pagina: search. */
(() => {
    'use strict';
    const {$, element, notify, safeNext, loginURL, token, storeToken, request, busy, confirmAction, empty, safeProductLink, currency, date, getProfile, setProfile} = window.HunterUI;
    function initSearch() {
        window.HunterAutocomplete?.attach($('productName'), () => $('searchForm').requestSubmit());
        const ids = ['productName', 'minPrice', 'maxPrice', 'storeFilter', 'sortOrder', 'shippingFilter'];
        const keys = ['q', 'min', 'max', 'loja', 'ordem', 'frete'];
        const query = new URLSearchParams(location.search);
        const selectedStore = query.get('loja');
        if (selectedStore && !Array.from($('storeFilter').options).some(o => o.value === selectedStore)) {
            const option = element('option', '', selectedStore); option.value = selectedStore;
            $('storeFilter').append(option);
        }
        request('/lojas').then(data => {
            (data.lojas || []).forEach(store => {
                if (!Array.from($('storeFilter').options).some(o => o.value === store)) {
                    const option = element('option', '', store); option.value = store;
                    $('storeFilter').append(option);
                }
            });
        }).catch(() => {}); // Opcoes legadas continuam disponiveis se API indisponivel.
        ids.forEach((id, index) => { if (query.has(keys[index])) $(id).value = query.get(keys[index]); });
        $('preferObserved').checked = query.get('priorizar_observados') !== 'false';
        if (!$('sortOrder').value) $('sortOrder').value = 'priceAsc';
        if (!$('shippingFilter').value) $('shippingFilter').value = 'all';
        let currentPage = 1, total = 0, shown = 0, controller, filterTimer, generation = 0;
        let activeTerm = $('productName').value.trim();

        function persist() {
            const params = new URLSearchParams();
            ids.forEach((id, index) => {
                const value = id === 'productName' ? activeTerm : $(id).value;
                if (value) params.set(keys[index], value);
            });
            if (!$('preferObserved').checked) params.set('priorizar_observados', 'false');
            history.replaceState(null, '', 'buscar.html' + (params.size ? '?' + params : ''));
            sessionStorage.setItem('hunterSearchURL', location.href);
        }

        function validFilters() {
            const min = $('minPrice').value, max = $('maxPrice').value;
            const invalid = !$('minPrice').validity.valid || !$('maxPrice').validity.valid;
            const reversed = min !== '' && max !== '' && Number(min) > Number(max);
            $('filterError').hidden = !invalid && !reversed;
            $('filterError').textContent = invalid ? 'Informe valores válidos, com até duas casas decimais.' : 'O mínimo não pode ser maior que o máximo.';
            return !invalid && !reversed;
        }

        function productCard(product) {
            const card = element('article', 'product-card');
            card.dataset.catalogOrigin = product.produto_id ? 'observed' : 'legacy';
            if (product.produto_id) card.dataset.productId = product.produto_id;
            const image = element('img', 'product-image');
            const placeholder = 'imgfeature/product-placeholder.svg';
            image.alt = product.nome; image.width = 320; image.height = 180;
            image.loading = 'lazy'; image.referrerPolicy = 'no-referrer';
            let imageURL;
            try {
                const parsed = new URL(product.imagem_url);
                if (parsed.protocol === 'https:' && !parsed.username && !parsed.password) imageURL = parsed.href;
            } catch (_) { /* Produto sem imagem: usar fallback local. */ }
            image.onerror = () => { image.onerror = null; image.src = placeholder; };
            image.src = imageURL || placeholder;
            card.append(image);
            card.append(element('span', 'tag store', product.loja || 'Loja online'), element('h3', '', product.nome),
                element('p', 'product-price', currency(product.preco)));
            if (product.pagamento) card.append(element('p', 'hint', 'Preço no ' + product.pagamento));
            if (product.preco_cartao != null) card.append(element('p', 'hint', currency(product.preco_cartao) + ' no cartão; condições na loja'));
            if (product.price_kind === 'promotional') card.append(element('p', 'hint', 'Preço promocional: ' + (product.promotion_terms || 'confirme as condições na loja')));
            card.append(element('p', 'hint', product.frete_observacao || (product.frete_gratis === true ? 'Frete grátis; confirme condições na loja' : 'Consulte o frete na loja conforme seu CEP')));
            if (product.coletado_em) card.append(element('p', 'hint', (product.fonte_coleta === 'captura_publica' ? 'Captura pública consultada em ' : 'Coletado em ') + date(product.coletado_em) + '. Confirme preço e estoque na loja.'));
            else card.append(element('p', 'hint', 'Preço legado sem data de coleta. Confirme na loja.'));
            if (product.produto_id && product.historico_disponivel) {
                const details = element('details', 'price-history');
                details.append(element('summary', '', 'Histórico de preços'));
                const list = element('ol');
                const more = element('button', 'button secondary', 'Carregar histórico');
                more.type = 'button';
                const status = element('p', 'hint'); status.setAttribute('role', 'status');
                let page = 0, loading = false;
                async function loadHistory() {
                    if (loading) return;
                    loading = true; more.disabled = true; status.textContent = 'Carregando...';
                    try {
                        const data = await request(`/produtos/${product.produto_id}/historico?pagina=${page + 1}&limite=10`);
                        data.historico.forEach(row => list.append(element('li', '',
                            `${new Date(row.coletado_em).toLocaleString('pt-BR')}: ${currency(row.preco)}${row.disponivel ? '' : ' (indisponível)'}`)));
                        page++; status.textContent = `${list.children.length} de ${data.total} observações`;
                        more.hidden = list.children.length >= data.total; more.textContent = 'Ver mais';
                    } catch (_) { status.textContent = 'Não foi possível carregar o histórico. Tente novamente.'; }
                    finally { loading = false; more.disabled = false; }
                }
                details.addEventListener('toggle', () => { if (details.open && page === 0) loadHistory(); });
                more.addEventListener('click', loadHistory);
                details.append(list, status, more); card.append(details);
            }
            const actions = element('div', 'card-actions');
            const href = safeProductLink(product.link);
            if (href) {
                const link = element('a', 'button primary', 'Ver oferta na loja ↗');
                link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer';
                actions.append(link);
            } else actions.append(element('span', 'hint', 'Link indisponível'));
            const alert = element('button', 'button secondary', 'Criar alerta de preço');
            alert.type = 'button';
            alert.addEventListener('click', () => {
                const target = 'alertas.html?' + new URLSearchParams({produto: product.nome, preco: Number(product.preco).toFixed(2)});
                location.href = token() ? target : loginURL(target);
            });
            actions.append(alert); card.append(actions);
            return card;
        }

        async function search(append = false) {
            clearTimeout(filterTimer);
            if (!validFilters()) {
                generation++; controller?.abort();
                $('resultList').replaceChildren(); $('loadMore').hidden = true;
                $('resultsCount').textContent = 'Corrija a faixa de preço para continuar.';
                $('searchState').replaceChildren(); return;
            }
            const term = activeTerm;
            if (!term) return;
            controller?.abort(); controller = new AbortController();
            const currentController = controller;
            const ticket = ++generation;
            const params = new URLSearchParams({nome: term, pagina: append ? currentPage + 1 : 1, limite: 24, ordem: $('sortOrder').value});
            params.set('priorizar_observados', String($('preferObserved').checked));
            $('searchPriorityNote').textContent = $('preferObserved').checked
                ? 'Catálogo datado primeiro; preço ordenado dentro de cada grupo. Desmarque a prioridade para ordenar todos os registros por preço.'
                : 'Todos os registros ordenados por preço, incluindo legados sem imagem ou data de coleta.';
            if ($('minPrice').value !== '') params.set('preco_min', $('minPrice').value);
            if ($('maxPrice').value !== '') params.set('preco_max', $('maxPrice').value);
            if ($('storeFilter').value) params.set('loja', $('storeFilter').value);
            if ($('shippingFilter').value === 'free') params.set('frete_gratis', 'true');
            persist();
            $('searchState').replaceChildren();
            $('loadMore').hidden = true;
            $('resultList').setAttribute('aria-busy', 'true');
            if (!append) {
                shown = 0; currentPage = 1;
                $('resultList').replaceChildren(...Array.from({length: 6}, () => element('div', 'skeleton')));
            }
            $('resultsCount').textContent = 'Buscando ofertas...';
            try {
                const data = await request('/buscar-produtos?' + params, {signal: currentController.signal});
                if (ticket !== generation) return;
                const products = Array.isArray(data.produtos) ? data.produtos : [];
                total = data.total || 0; currentPage = data.pagina;
                if (!append) $('resultList').replaceChildren();
                $('resultList').append(...products.map(productCard));
                shown += products.length;
                $('resultsCount').textContent = `${shown} de ${total} oferta${total === 1 ? '' : 's'}`;
                const normalized = term.toLowerCase();
                const category = ['mouse', 'teclado', 'monitor', 'pendrive'].find(name => normalized.includes(name));
                $('categoryLabel').replaceChildren();
                if (category) {
                    const image = element('img'); image.src = `imgfeature/${category}.png`; image.alt = '';
                    image.width = 28; image.height = 28; image.style.objectFit = 'contain';
                    $('categoryLabel').append(image, document.createTextNode(' Ofertas para ' + term));
                }
                $('loadMore').hidden = shown >= total;
                if (!total) empty($('searchState'), 'Ainda não encontramos essa oferta', 'Tente um termo mais curto ou ajuste os filtros de preço e loja.');
            } catch (error) {
                if (ticket !== generation || currentController.signal.aborted) return;
                if (!append) $('resultList').replaceChildren();
                $('resultsCount').textContent = append ? `${shown} de ${total} ofertas` : 'Consulta indisponível';
                const retry = element('button', 'button secondary', 'Tentar novamente');
                retry.addEventListener('click', () => search(append));
                empty($('searchState'), 'Vamos tentar novamente?', error.message, retry);
            } finally {
                if (ticket === generation) $('resultList').removeAttribute('aria-busy');
            }
        }

        $('searchForm').addEventListener('submit', event => {
            event.preventDefault();
            activeTerm = $('productName').value.trim();
            if (activeTerm) search();
        });
        ['minPrice', 'maxPrice', 'storeFilter', 'sortOrder', 'shippingFilter', 'preferObserved'].forEach(id => {
            $(id).addEventListener(id.includes('Price') ? 'input' : 'change', () => {
                clearTimeout(filterTimer);
                filterTimer = setTimeout(() => search(), 300);
            });
        });
        $('clearFilters').addEventListener('click', () => {
            $('minPrice').value = ''; $('maxPrice').value = ''; $('storeFilter').value = ''; $('sortOrder').value = 'priceAsc';
            $('preferObserved').checked = true;
            $('shippingFilter').value = 'all';
            $('filterError').hidden = true; search();
        });
        $('loadMore').addEventListener('click', () => search(true));
        if (activeTerm) search();
        else empty($('searchState'), 'Encontre uma boa compra', 'Digite o nome do produto para comparar as ofertas disponíveis.');
    }
    window.HunterPages.search = initSearch;
})();
