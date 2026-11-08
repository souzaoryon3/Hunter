/* Dashboard somente leitura. Graficos SVG locais, sem CDN ou bibliotecas remotas. */
(() => {
    'use strict';
    const $ = id => document.getElementById(id);
    const api = window.HunterAPI.apiBase;
    const money = n => n == null ? '—' : Number(n).toLocaleString('pt-BR', {style:'currency', currency:'BRL'});
    const percent = n => n == null ? 'Sem comparação' : `${Number(n).toLocaleString('pt-BR', {maximumFractionDigits:2})}%`;
    let controller, historyController, revision = 0;
    const chartState = new WeakMap();
    const resizeObserver = new ResizeObserver(entries => entries.forEach(entry => {
        const saved = chartState.get(entry.target);
        const width = Math.round(entry.contentRect.width);
        if (saved && width > 0 && saved.width !== width) chart(entry.target, saved.points, saved.scatter);
    }));
    function el(tag, text, cls) {
        const node = document.createElement(tag); if (text != null) node.textContent = text;
        if (cls) node.className = cls; return node;
    }
    function svgEl(tag, attrs, text) {
        const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
        Object.entries(attrs).forEach(([k,v]) => node.setAttribute(k, v));
        if (text != null) node.textContent = text; return node;
    }
    async function get(path, params, signal) {
        const response = await fetch(api + path + '?' + new URLSearchParams(params), {signal});
        if (!response.ok) throw new Error(response.status === 413 ? 'Muitas observações: reduza o período.' : 'Não foi possível consultar as análises. Tente novamente.');
        return response.json();
    }
    function options() { return {origem:$('dataOrigin').value, dias:$('analysisDays').value}; }
    function chart(container, points, scatter=false) {
        container.replaceChildren();
        if (!points.length) { container.append(el('p','Sem observações para desenhar o gráfico.','hint')); return; }
        const measured=Math.round(container.clientWidth);
        chartState.set(container,{points,scatter,width:measured}); resizeObserver.observe(container);
        const width=Math.max(260,Math.min(680,measured || 680)), height=260, left=72, right=26, top=20, bottom=52;
        const xs=points.map(p=>p.x), ys=points.flatMap(p=>p.average==null ? [p.y] : [p.y,p.average]);
        const minX=Math.min(...xs), maxX=Math.max(...xs);
        let minY=Math.min(...ys), maxY=Math.max(...ys);
        if (minY===maxY) { minY-=Math.max(1,Math.abs(minY)*.05); maxY+=Math.max(1,Math.abs(maxY)*.05); }
        const x=n=>left+(maxX===minX ? .5 : (n-minX)/(maxX-minX))*(width-left-right);
        const y=n=>top+(1-(n-minY)/(maxY-minY))*(height-top-bottom);
        const svg=svgEl('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':scatter ? 'Grupos por preço médio e variação percentual' : 'Preço observado e média móvel de três observações'});
        for (let i=0;i<4;i++) {
            const value=minY+(maxY-minY)*i/3;
            svg.append(svgEl('line',{x1:left,x2:width-right,y1:y(value),y2:y(value),stroke:'#dce2d8'}));
            svg.append(svgEl('text',{x:left-8,y:y(value)+4,'text-anchor':'end',fill:'#526348','font-size':11},scatter ? percent(value) : money(value)));
        }
        const label=n=>scatter ? money(n) : new Date(n).toLocaleDateString('pt-BR');
        svg.append(svgEl('text',{x:left,y:height-17,fill:'#526348','font-size':11},label(minX)));
        if (maxX!==minX) svg.append(svgEl('text',{x:width-right,y:height-17,'text-anchor':'end',fill:'#526348','font-size':11},label(maxX)));
        if (!scatter) {
            svg.append(svgEl('polyline',{points:points.map(p=>`${x(p.x)},${y(p.y)}`).join(' '),fill:'none',stroke:'#345a36','stroke-width':3}));
            const averaged=points.filter(p=>p.average!=null);
            svg.append(svgEl('polyline',{points:averaged.map(p=>`${x(p.x)},${y(p.average)}`).join(' '),fill:'none',stroke:'#bd7900','stroke-width':2,'stroke-dasharray':'6 4'}));
        }
        const colors=['#345a36','#b26419','#486da0','#984d7c','#637500'];
        points.forEach(p=>{
            const dot=svgEl('circle',{cx:x(p.x),cy:y(p.y),r:scatter ? 6 : 4,fill:scatter ? colors[(p.group-1)%colors.length] : '#345a36',tabindex:0});
            dot.append(svgEl('title',{},p.label)); svg.append(dot);
        });
        container.append(svg);
    }
    function renderStats(data) {
        ['produtos','observacoes','quedas','oportunidades'].forEach(key=>$(key+'Metric').textContent=data.resumo[key]);
        $('analysisNote').textContent=data.mensagem;
        $('statsBody').replaceChildren(); $('productSelect').replaceChildren();
        data.produtos.forEach(p=>{
            const row=el('tr');
            [p.nome,p.loja,p.observacoes,money(p.preco_atual),money(p.preco_medio),money(p.preco_minimo),money(p.preco_maximo),percent(p.variacao_percentual)]
                .forEach(value=>row.append(el('td',value)));
            $('statsBody').append(row);
            const option=el('option',p.nome); option.value=p.produto_id; $('productSelect').append(option);
        });
        $('emptyAnalysis').hidden=data.produtos.length>0;
        $('analysisPanels').hidden=!data.produtos.length;
        $('opportunityList').replaceChildren();
        const opportunities=data.produtos.filter(p=>p.oportunidade);
        if (!opportunities.length) $('opportunityList').append(el('p','Nenhuma oportunidade atende aos critérios neste período. Uma única observação não permite detectar queda.','hint'));
        opportunities.forEach(p=>{
            const item=el('article',null,'insight-item');
            item.append(el('strong',p.nome),el('p',`${money(p.preco_atual)} · queda de ${percent(p.queda_recente_percentual)} ante a observação anterior`),el('p',`Coletado em ${new Date(p.ultima_observacao).toLocaleString('pt-BR')}. Confirme preço e estoque na loja.`,'hint'));
            $('opportunityList').append(item);
        });
    }
    function renderClusters(data) {
        $('clusterNote').textContent=data.mensagem;
        chartState.delete($('clusterChart'));
        $('clusterChart').replaceChildren(); $('clusterGroups').replaceChildren();
        if (data.status!=='ok') return;
        chart($('clusterChart'),data.produtos.map(p=>({x:p.preco_medio,y:p.variacao_percentual,group:p.grupo,label:`Grupo ${p.grupo}: ${p.nome}, média ${money(p.preco_medio)}, variação ${percent(p.variacao_percentual)}`})),true);
        data.grupos.forEach(g=>$('clusterGroups').append(el('p',`Grupo ${g.grupo}: ${g.produtos} produtos · média ${money(g.preco_medio)} · variação ${percent(g.variacao_media_percentual)}`,'hint')));
    }
    async function loadHistory() {
        historyController?.abort(); historyController=new AbortController();
        const version=revision, signal=historyController.signal;
        chartState.delete($('priceChart'));
        $('priceChart').replaceChildren(el('p','Carregando histórico…','hint'));
        $('historyBody').replaceChildren();
        try {
            const data=await get('/analytics/historico/'+$('productSelect').value,options(),signal);
            if (signal.aborted || version!==revision) return;
            chart($('priceChart'),data.serie.map(p=>({x:Date.parse(p.coletado_em),y:p.preco,average:p.media_movel_3,label:`${new Date(p.coletado_em).toLocaleString('pt-BR')}: ${money(p.preco)}`})));
            $('historyNote').textContent=data.serie.length<2 ? 'Uma observação: ainda não há tendência ou variação para comparar.' : 'Linha verde: preço observado. Linha tracejada: média móvel de 3 observações, sem interpolar dias ausentes.';
            data.serie.forEach(p=>{
                const row=el('tr'); [new Date(p.coletado_em).toLocaleString('pt-BR'),money(p.preco),money(p.media_movel_3)]
                    .forEach(value=>row.append(el('td',value))); $('historyBody').append(row);
            });
        } catch (err) {
            if (err.name!=='AbortError' && version===revision) $('priceChart').replaceChildren(el('p',err.message,'hint'));
        }
    }
    async function load() {
        controller?.abort(); historyController?.abort(); controller=new AbortController();
        const signal=controller.signal, version=++revision;
        $('dashboardContent').hidden=true; $('dashboardError').hidden=true;
        $('dashboardState').textContent='Carregando observações e calculando análises…';
        $('sourceBadge').textContent=$('dataOrigin').value==='demo' ? 'Demonstração • dados sintéticos' : 'Dados reais • histórico observado';
        $('sourceBadge').classList.toggle('demo-badge',$('dataOrigin').value==='demo');
        $('refreshAnalysis').disabled=true;
        try {
            const [stats,groups]=await Promise.all([get('/analytics/estatisticas',options(),signal),get('/analytics/agrupamentos',{...options(),k:$('clusterCount').value},signal)]);
            if (signal.aborted || version!==revision) return;
            $('sourceNote').textContent=stats.aviso;
            renderStats(stats); renderClusters(groups);
            $('dashboardContent').hidden=false; $('dashboardState').textContent='Análises atualizadas.';
            if (stats.produtos.length) await loadHistory();
        } catch (err) {
            if (err.name!=='AbortError' && version===revision) {
                $('dashboardState').textContent='Consulta indisponível.';
                $('dashboardError').hidden=false; $('dashboardErrorText').textContent=err.message;
            }
        } finally { if (version===revision) $('refreshAnalysis').disabled=false; }
    }
    $('analysisForm').addEventListener('submit',event=>{event.preventDefault();load();});
    ['dataOrigin','analysisDays','clusterCount'].forEach(id=>$(id).addEventListener('change',load));
    $('productSelect').addEventListener('change',loadHistory);
    $('retryAnalysis').addEventListener('click',load);
    load();
})();
