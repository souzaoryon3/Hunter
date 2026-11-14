/* Comportamento da pagina: home. */
(() => {
    'use strict';
    const {$, element, notify, safeNext, loginURL, token, storeToken, request, busy, confirmAction, empty, safeProductLink, currency, date, getProfile, setProfile} = window.HunterUI;
    function initHome() {
        window.HunterAutocomplete?.attach($('homeQuery'), () => $('homeSearch').requestSubmit());
        $('homeSearch').addEventListener('submit', event => {
            event.preventDefault();
            const query = $('homeQuery').value.trim();
            if (query) location.href = 'buscar.html?q=' + encodeURIComponent(query);
        });
    }
    window.HunterPages.home = initHome;
})();
