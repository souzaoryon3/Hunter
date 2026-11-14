/* Sugestoes derivadas do PLN do catalogo; busca livre continua disponivel. */
(() => {
    'use strict';
    function attach(input, onSelect) {
        if (!input || input.dataset.autocompleteAttached) return;
        input.dataset.autocompleteAttached = 'true';
        const wrapper = document.createElement('div'); wrapper.className = 'autocomplete-field';
        input.before(wrapper); wrapper.append(input);
        const list = document.createElement('ul'); list.className = 'autocomplete-options';
        list.id = input.id + '-suggestions'; list.hidden = true; list.setAttribute('role', 'listbox');
        list.setAttribute('aria-label', 'Sugestões de produtos');
        const status = document.createElement('span'); status.className = 'sr-only';
        status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
        wrapper.append(list, status);
        input.setAttribute('role', 'combobox'); input.setAttribute('aria-autocomplete', 'list');
        input.setAttribute('aria-controls', list.id); input.setAttribute('aria-expanded', 'false');
        input.setAttribute('autocomplete', 'off');
        let timer, controller, generation = 0, active = -1, items = [], composing = false;

        function close() {
            list.hidden = true; list.replaceChildren(); items = []; active = -1;
            input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant');
            status.textContent = '';
        }
        function cancel() {
            generation++; clearTimeout(timer); controller?.abort(); close();
        }
        function choose(index) {
            const chosen = items[index];
            if (!chosen) return;
            input.value = chosen.texto; cancel(); onSelect?.(chosen);
        }
        function highlight(index) {
            active = index;
            Array.from(list.children).forEach((option, i) => option.setAttribute('aria-selected', String(i === active)));
            input.setAttribute('aria-activedescendant', list.children[active].id);
            list.children[active].scrollIntoView({block: 'nearest'});
        }
        function schedule() {
            cancel();
            const query = input.value.trim();
            if (query.length < 2 || query.length > 80 || composing) return;
            const ticket = generation;
            timer = setTimeout(async () => {
                controller = new AbortController();
                try {
                    const data = await window.HunterAPI.request('/sugestoes?' + new URLSearchParams({q: query}), {signal: controller.signal});
                    if (ticket !== generation || input.value.trim() !== query || document.activeElement !== input) return;
                    items = (Array.isArray(data.sugestoes) ? data.sugestoes : [])
                        .filter(item => typeof item.texto === 'string').slice(0, 8);
                    if (!items.length) { close(); return; }
                    items.forEach((item, index) => {
                        const option = document.createElement('li'); option.id = list.id + '-' + index;
                        option.setAttribute('role', 'option'); option.setAttribute('aria-selected', 'false');
                        option.textContent = item.texto;
                        option.addEventListener('pointerdown', event => event.preventDefault());
                        option.addEventListener('click', () => choose(index)); list.append(option);
                    });
                    list.hidden = false; input.setAttribute('aria-expanded', 'true');
                    status.textContent = `${items.length} sugestões. Use as setas e Enter para selecionar.`;
                } catch (_) {
                    if (ticket === generation) close();
                }
            }, 220);
        }
        input.addEventListener('input', schedule);
        input.addEventListener('focus', schedule);
        input.addEventListener('blur', cancel);
        input.addEventListener('compositionstart', () => { composing = true; cancel(); });
        input.addEventListener('compositionend', () => { composing = false; schedule(); });
        input.form?.addEventListener('submit', cancel);
        input.addEventListener('keydown', event => {
            if (event.isComposing) return;
            if (event.key === 'Escape') { event.preventDefault(); cancel(); }
            else if (!list.hidden && items.length && ['ArrowDown', 'ArrowUp'].includes(event.key)) {
                event.preventDefault();
                highlight(event.key === 'ArrowDown' ? (active + 1) % items.length : (active < 0 ? items.length - 1 : (active - 1 + items.length) % items.length));
            } else if (event.key === 'Enter' && !list.hidden && active >= 0) {
                event.preventDefault(); choose(active);
            }
        });
    }
    window.HunterAutocomplete = {attach};
})();
