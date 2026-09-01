<script>
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { api, assetUrl } from '$lib/api.js';
  import QueryEditor from '$lib/components/QueryEditor.svelte';
  import ColorPalette from '$lib/components/ColorPalette.svelte';

  const id = $page.params.id;

  let form = {
    slug: '', nome: '', descricao: '',
    sql_texto: '', tipo: 'kpi',
    empresa_id: null, cache_ttl: 300, ativo: true,
    kpi_cor_fonte: '#e6edf3', kpi_cor_fundo: '#161b22',
    mapa_camada: 'padrao',
    chart_fonte_tamanho: 12, chart_truncar_label: false,
    chart_truncar_tamanho: 15, chart_mostrar_valor: false,
    chart_valor_label: '',
    chart_filtro_coluna: '',
    impressao_habilitada: false, impressao_caminho: '', impressao_coluna: '',
    meta_habilitada: false, meta_coluna_valor: '', meta_coluna_inicio: '',
    meta_coluna_fim: '', meta_cor_dentro: '#3fb950', meta_cor_fora: '#f85149',
    subquery_id: null,
    pdf_orientacao: 'retrato',
    kpi_imagem_habilitada: false, kpi_imagem_posicao: 'direita',
    kpi_valor_primeiro: false,
    grupo_nome: '',
  };

  let kpiImagemFile    = null;
  let kpiImagemPreview = null;
  let kpiImagemUrlAtual = null;

  function onKpiImagemChange(e) {
    kpiImagemFile = e.target.files[0];
    if (kpiImagemFile) {
      kpiImagemPreview = URL.createObjectURL(kpiImagemFile);
    }
  }

  // cada item: { nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, _testar_valor }
  let params          = [];
  let testarEmpresaId = null;
  let empresas        = [];
  let variaveis       = [];
  let carregando      = true;
  let resultadoTeste  = null;
  let salvando        = false;
  let erro            = null;
  let agrupamentos       = []; // [{coluna, ordem}]
  let agregacoes         = []; // [{coluna, funcao, label, ordem}]
  let queriesDisponiveis = [];
  let subqueryParams     = []; // parâmetros da query_parametros da subconsulta escolhida
  let mapeamentoSubquery = []; // [{coluna_origem, parametro_destino}] — mesmo tamanho de subqueryParams

  const tipos = [
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context', 'map', 'table_dynamic'
  ];

  $: gruposExistentes = [...new Set(queriesDisponiveis.map(q => q.grupo_nome).filter(Boolean))].sort();

  onMount(async () => {
    try {
      const [q, emps, prms, vars, qs] = await Promise.all([
        api.buscarQuery(id),
        api.listarEmpresas(),
        api.parametrosQuery(id),
        api.listarVariaveis(),
        api.listarQueries(),
      ]);
      empresas  = emps;
      variaveis = vars.filter(v => v.ativo);
      queriesDisponiveis = qs;
      if (emps.length > 0) testarEmpresaId = emps[0].id;
      form = {
        slug:          q.slug,
        nome:          q.nome,
        descricao:     q.descricao || '',
        sql_texto:     q.sql_texto,
        tipo:          q.tipo,
        empresa_id:    q.empresa_id,
        cache_ttl:     q.cache_ttl,
        ativo:         q.ativo,
        kpi_cor_fonte: q.kpi_cor_fonte || '#e6edf3',
        kpi_cor_fundo: q.kpi_cor_fundo || '#161b22',
        mapa_camada:   q.mapa_camada || 'padrao',
        chart_fonte_tamanho:   q.chart_fonte_tamanho ?? 12,
        chart_truncar_label:   q.chart_truncar_label ?? false,
        chart_truncar_tamanho: q.chart_truncar_tamanho ?? 15,
        chart_mostrar_valor:   q.chart_mostrar_valor ?? false,
        chart_valor_label:     q.chart_valor_label || '',
        chart_filtro_coluna:   q.chart_filtro_coluna || '',
        impressao_habilitada: q.impressao_habilitada ?? false,
        impressao_caminho:    q.impressao_caminho || '',
        impressao_coluna:     q.impressao_coluna || '',
        meta_habilitada:    q.meta_habilitada ?? false,
        meta_coluna_valor:  q.meta_coluna_valor || '',
        meta_coluna_inicio: q.meta_coluna_inicio || '',
        meta_coluna_fim:    q.meta_coluna_fim || '',
        meta_cor_dentro:    q.meta_cor_dentro || '#3fb950',
        meta_cor_fora:      q.meta_cor_fora || '#f85149',
        subquery_id:        q.subquery_id ?? null,
        pdf_orientacao:        q.pdf_orientacao || 'retrato',
        kpi_imagem_habilitada: q.kpi_imagem_habilitada ?? false,
        kpi_imagem_posicao:    q.kpi_imagem_posicao || 'direita',
        kpi_valor_primeiro:    q.kpi_valor_primeiro ?? false,
        grupo_nome:            q.grupo_nome || '',
      };
      kpiImagemUrlAtual = q.kpi_imagem_url ? assetUrl(q.kpi_imagem_url) : null;
      params = prms.map(p => ({ ...p, _testar_valor: '' }));

      if (q.tipo === 'table_dynamic') {
        agrupamentos = await api.agrupamentosQuery(id);
        agregacoes   = await api.agregacoesQuery(id);
        if (q.subquery_id) {
          subqueryParams = await api.parametrosQuery(q.subquery_id);
          const salvos = await api.subqueryParametrosQuery(id);
          mapeamentoSubquery = subqueryParams.map((p, idx) => {
            const existente = salvos.find(s => s.parametro_destino === p.nome);
            return { coluna_origem: existente?.coluna_origem ?? '', parametro_destino: p.nome, ordem: idx };
          });
        }
      }
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  });

  function onVariavelChange(p, idx) {
    if (!p.variavel_id) {
      p.nome = '';
      p.tipo = 'text';
      p.param_slot = null;
      params = [...params];
      return;
    }
    const v = variaveis.find(x => x.id === Number(p.variavel_id));
    if (!v) return;

    if (v.tipo === 'date_range') {
      const base = { variavel_id: v.id, tipo: v.tipo, obrigatorio: p.obrigatorio, valor_padrao: '', descricao: '', _testar_valor: '' };
      const rowI = { ...base, nome: v.slug + '_inicio', param_slot: 'inicio' };
      const rowF = { ...base, nome: v.slug + '_fim',    param_slot: 'fim'   };
      params = [...params.slice(0, idx), rowI, rowF, ...params.slice(idx + 1)];
    } else {
      p.nome = v.slug;
      p.tipo = v.tipo;
      p.param_slot = null;
      params = [...params];
    }
  }

  function adicionarParam() {
    params = [...params, {
      nome: '', tipo: 'text', obrigatorio: false,
      valor_padrao: '', descricao: '',
      variavel_id: null, _testar_valor: ''
    }];
  }

  function removerParam(i) {
    params = params.filter((_, idx) => idx !== i);
    resultadoTeste = null;
  }

  function adicionarAgrupamento() {
    agrupamentos = [...agrupamentos, { coluna: '', ordem: agrupamentos.length }];
  }
  function removerAgrupamento(i) {
    agrupamentos = agrupamentos.filter((_, idx) => idx !== i).map((a, idx) => ({ ...a, ordem: idx }));
  }
  function moverAgrupamento(i, direcao) {
    const j = i + direcao;
    if (j < 0 || j >= agrupamentos.length) return;
    const copia = [...agrupamentos];
    [copia[i], copia[j]] = [copia[j], copia[i]];
    agrupamentos = copia.map((a, idx) => ({ ...a, ordem: idx }));
  }

  function adicionarAgregacao() {
    agregacoes = [...agregacoes, { coluna: '', funcao: 'soma', label: '', ordem: agregacoes.length }];
  }
  function removerAgregacao(i) {
    agregacoes = agregacoes.filter((_, idx) => idx !== i).map((a, idx) => ({ ...a, ordem: idx }));
  }

  async function onSubqueryChange() {
    mapeamentoSubquery = [];
    if (!form.subquery_id) {
      subqueryParams = [];
      return;
    }
    subqueryParams = await api.parametrosQuery(form.subquery_id);
    mapeamentoSubquery = subqueryParams.map((p, idx) => ({ coluna_origem: '', parametro_destino: p.nome, ordem: idx }));
  }

  async function testar(sql) {
    const testar_parametros = params.map(p => ({
      nome:  p.nome,
      valor: p._testar_valor !== '' ? p._testar_valor : (p.valor_padrao || null)
    }));

    const res = await api.testarQuery({
      ...form,
      sql_texto: sql,
      testar_empresa_id: testarEmpresaId,
      testar_parametros,
    });
    resultadoTeste = res;
    return res;
  }

  async function salvar() {
    if (!form.nome.trim()) {
      erro = 'Nome legível é obrigatório.';
      return;
    }
    if (!form.slug.trim()) {
      erro = 'Slug é obrigatório.';
      return;
    }
    erro = null;
    salvando = true;
    try {
      await api.atualizarQuery(id, {
        slug:          form.slug,
        nome:          form.nome,
        descricao:     form.descricao,
        sql_texto:     form.sql_texto,
        tipo:          form.tipo,
        cache_ttl:     form.cache_ttl,
        ativo:         form.ativo,
        kpi_cor_fonte: form.kpi_cor_fonte,
        kpi_cor_fundo: form.kpi_cor_fundo,
        mapa_camada:   form.mapa_camada,
        chart_fonte_tamanho:   form.chart_fonte_tamanho,
        chart_truncar_label:   form.chart_truncar_label,
        chart_truncar_tamanho: form.chart_truncar_tamanho,
        chart_mostrar_valor:   form.chart_mostrar_valor,
        chart_valor_label:     form.chart_valor_label,
        chart_filtro_coluna:   form.chart_filtro_coluna || null,
        impressao_habilitada: form.impressao_habilitada,
        impressao_caminho:    form.impressao_caminho || null,
        impressao_coluna:     form.impressao_coluna || null,
        meta_habilitada:    form.meta_habilitada,
        meta_coluna_valor:  form.meta_coluna_valor || null,
        meta_coluna_inicio: form.meta_coluna_inicio || null,
        meta_coluna_fim:    form.meta_coluna_fim || null,
        meta_cor_dentro:    form.meta_cor_dentro,
        meta_cor_fora:      form.meta_cor_fora,
        subquery_id:        form.subquery_id,
        pdf_orientacao:        form.pdf_orientacao,
        kpi_imagem_habilitada: form.kpi_imagem_habilitada,
        kpi_imagem_posicao:    form.kpi_imagem_posicao,
        kpi_valor_primeiro:    form.kpi_valor_primeiro,
        grupo_nome:            form.grupo_nome,
      });
      if (form.tipo === 'kpi' && kpiImagemFile) {
        const fd = new FormData();
        fd.append('file', kpiImagemFile);
        await api.uploadKpiImagem(id, fd);
      }
      await api.salvarParametrosQuery(id, params.map(({ _testar_valor, ...p }) => p));
      if (form.tipo === 'table_dynamic') {
        await api.salvarAgrupamentosQuery(id, agrupamentos.filter(a => a.coluna));
        await api.salvarAgregacoesQuery(id, agregacoes.filter(a => a.coluna));
        if (form.subquery_id) {
          await api.salvarSubqueryParametrosQuery(
            id,
            mapeamentoSubquery.filter(m => m.coluna_origem)
          );
        }
      }
      goto('/configuracoes/queries');
    } catch (e) {
      erro = e.message;
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Editar Query — GPA Analytics</title></svelte:head>

<div style="padding:24px; max-width:860px; margin:0 auto;">
  <div style="display:flex; align-items:center; gap:16px; margin-bottom:24px;">
    <a href="/configuracoes/queries" style="color:var(--muted)">← Voltar</a>
    <h2 style="font-family:var(--font-display)">Editar Query</h2>
  </div>

  {#if carregando}
    <p style="color:var(--muted)">Carregando...</p>
  {:else if erro && !form.slug}
    <p class="error">{erro}</p>
  {:else}
    <div class="card" style="display:flex; flex-direction:column; gap:16px;">
      <!-- Identificação -->
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
        <label class="lbl">
          Slug (identificador único)
          <input bind:value={form.slug} placeholder="ex: kpi_receita" />
        </label>
        <label class="lbl">
          Nome legível
          <input bind:value={form.nome} />
        </label>
      </div>
      <p class="hint-block">
        Cuidado ao mudar o slug: indicadores de painel e o mapeamento de subconsulta referenciam a query por esse slug como texto puro — mudar aqui não atualiza essas referências automaticamente.
      </p>

      <label class="lbl">
        Descrição
        <input bind:value={form.descricao} placeholder="Opcional" />
      </label>

      <label class="lbl">
        Grupo (opcional)
        <input bind:value={form.grupo_nome} list="grupos-lista" placeholder="ex: Perdas, Checklist" />
        <datalist id="grupos-lista">
          {#each gruposExistentes as g}<option value={g}></option>{/each}
        </datalist>
      </label>

      <label class="lbl">
        Tipo
        <select bind:value={form.tipo}>
          {#each tipos as t}<option value={t}>{t}</option>{/each}
        </select>
      </label>

      <label class="lbl">
        Cache TTL (segundos, 0 = sem cache)
        <input type="number" bind:value={form.cache_ttl} min="0" />
      </label>

      <label style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted);cursor:pointer">
        <input type="checkbox" bind:checked={form.ativo} />
        Ativo
      </label>

      {#if form.tipo === 'kpi'}
        <div class="kpi-cores">
          <span class="section-title">Cores do KPI</span>
          <div class="cores-row">
            <label class="lbl">
              Cor da fonte
              <div class="color-pick">
                <input type="color" bind:value={form.kpi_cor_fonte} />
                <input type="text"  bind:value={form.kpi_cor_fonte} placeholder="#e6edf3" style="width:90px" />
              </div>
              <ColorPalette bind:value={form.kpi_cor_fonte} />
            </label>
            <label class="lbl">
              Cor de fundo
              <div class="color-pick">
                <input type="color" bind:value={form.kpi_cor_fundo} />
                <input type="text"  bind:value={form.kpi_cor_fundo} placeholder="#161b22" style="width:90px" />
              </div>
              <ColorPalette bind:value={form.kpi_cor_fundo} />
            </label>
            <div class="kpi-preview" style="background:{form.kpi_cor_fundo}; color:{form.kpi_cor_fonte}">
              {#if form.kpi_valor_primeiro}
                <span class="kpi-preview-valor" style="color:{form.kpi_cor_fonte}">1.234</span>
                <span class="kpi-preview-label" style="color:{form.kpi_cor_fonte}; opacity:.7">LABEL</span>
              {:else}
                <span class="kpi-preview-label" style="color:{form.kpi_cor_fonte}; opacity:.7">LABEL</span>
                <span class="kpi-preview-valor" style="color:{form.kpi_cor_fonte}">1.234</span>
              {/if}
            </div>
          </div>
          <label class="check-inline">
            <input type="checkbox" bind:checked={form.kpi_valor_primeiro} />
            Mostrar o valor antes do label
          </label>
        </div>

        <div class="section-block">
          <span class="section-title">Imagem do KPI</span>
          <label class="check-inline">
            <input type="checkbox" bind:checked={form.kpi_imagem_habilitada} />
            Mostrar uma imagem dentro do card
          </label>
          {#if form.kpi_imagem_habilitada}
            <div class="cores-row">
              <label class="lbl">
                Arquivo da imagem
                <input type="file" accept="image/*" on:change={onKpiImagemChange} />
              </label>
              <label class="lbl">
                Posição da imagem
                <select bind:value={form.kpi_imagem_posicao}>
                  <option value="esquerda">Esquerda (valor fica à direita)</option>
                  <option value="direita">Direita (valor fica à esquerda)</option>
                </select>
              </label>
              {#if kpiImagemPreview}
                <img class="kpi-imagem-preview" src={kpiImagemPreview} alt="nova imagem do KPI" />
              {:else if kpiImagemUrlAtual}
                <img class="kpi-imagem-preview" src={kpiImagemUrlAtual} alt="imagem atual do KPI" />
              {/if}
            </div>
          {/if}
        </div>
      {/if}

      {#if form.tipo === 'table' || form.tipo === 'table_dynamic'}
        <div class="section-block">
          <span class="section-title">Orientação do PDF</span>
          <label class="lbl">
            Ao exportar esta tabela em PDF
            <select bind:value={form.pdf_orientacao}>
              <option value="retrato">Retrato</option>
              <option value="paisagem">Paisagem (tabelas largas)</option>
            </select>
          </label>
        </div>
      {/if}

      {#if form.tipo === 'map'}
        <div class="section-block">
          <span class="section-title">Camada do Mapa</span>
          <label class="lbl">
            Camada padrão
            <select bind:value={form.mapa_camada}>
              <option value="padrao">Padrão (tema claro/escuro)</option>
              <option value="satelite">Satélite</option>
            </select>
          </label>
        </div>
      {/if}

      {#if form.tipo === 'table'}
        <div class="section-block">
          <span class="section-title">Botão de Impressão</span>
          <label class="check-inline">
            <input type="checkbox" bind:checked={form.impressao_habilitada} />
            Habilitar botão de impressão nesta tabela
          </label>
          {#if form.impressao_habilitada}
            <label class="lbl">
              Caminho do relatório (concatenado após a URL base da empresa)
              <input type="text" bind:value={form.impressao_caminho} placeholder="relatorioPerda/Impressao.xhtml?uuid=" />
            </label>
            <label class="lbl">
              Coluna com o UUID/link (teste a query pra ver as colunas disponíveis)
              <select bind:value={form.impressao_coluna}>
                <option value="">— selecione —</option>
                {#each resultadoTeste?.colunas ?? (form.impressao_coluna ? [form.impressao_coluna] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
            <p class="hint-block">
              A coluna escolhida fica oculta na tabela do painel — usada só pra montar o link. O link final é
              <code>URL base da empresa + caminho acima + valor da coluna</code>. Sem URL base cadastrada na
              empresa (Configurações → Empresas), o botão não aparece pra ela, mesmo com o recurso habilitado aqui.
            </p>
          {/if}
        </div>
      {/if}

      {#if form.tipo === 'table'}
        <div class="section-block">
          <span class="section-title">Coloração por Meta</span>
          <label class="check-inline">
            <input type="checkbox" bind:checked={form.meta_habilitada} />
            Colorir uma coluna conforme uma meta (início/fim)
          </label>
          {#if form.meta_habilitada}
            <label class="lbl">
              Coluna a colorir (continua visível na tabela)
              <select bind:value={form.meta_coluna_valor}>
                <option value="">— selecione —</option>
                {#each resultadoTeste?.colunas ?? (form.meta_coluna_valor ? [form.meta_coluna_valor] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
            <label class="lbl">
              Coluna com o início da meta (fica oculta na tabela)
              <select bind:value={form.meta_coluna_inicio}>
                <option value="">— selecione —</option>
                {#each resultadoTeste?.colunas ?? (form.meta_coluna_inicio ? [form.meta_coluna_inicio] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
            <label class="lbl">
              Coluna com o fim da meta (fica oculta na tabela)
              <select bind:value={form.meta_coluna_fim}>
                <option value="">— selecione —</option>
                {#each resultadoTeste?.colunas ?? (form.meta_coluna_fim ? [form.meta_coluna_fim] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
            <div class="cores-row">
              <label class="lbl">
                Cor dentro da meta
                <div class="color-pick">
                  <input type="color" bind:value={form.meta_cor_dentro} />
                  <input type="text"  bind:value={form.meta_cor_dentro} placeholder="#3fb950" style="width:90px" />
                </div>
              </label>
              <label class="lbl">
                Cor fora da meta
                <div class="color-pick">
                  <input type="color" bind:value={form.meta_cor_fora} />
                  <input type="text"  bind:value={form.meta_cor_fora} placeholder="#f85149" style="width:90px" />
                </div>
              </label>
            </div>
            <p class="hint-block">
              Se o valor da coluna escolhida estiver entre início e fim (incluindo os limites), o texto
              fica na "cor dentro da meta"; fora disso, na "cor fora da meta". Linha sem meta definida ou
              com valor não numérico fica com a cor padrão, sem indicar dentro/fora.
            </p>
          {/if}
        </div>
      {/if}

      {#if form.tipo === 'table_dynamic'}
        <div class="section-block">
          <div class="section-header">
            <span class="section-title">Agrupamento</span>
            <button class="btn-ghost btn-sm" on:click={adicionarAgrupamento}>+ Nível</button>
          </div>
          {#if agrupamentos.length === 0}
            <p class="hint-block">Sem agrupamento — teste a query e adicione ao menos 1 nível.</p>
          {/if}
          {#each agrupamentos as ag, i}
            <div class="agrup-row">
              <span class="pos-badge">Nível {i + 1}</span>
              <select bind:value={ag.coluna}>
                <option value="">— selecione —</option>
                {#each resultadoTeste?.colunas ?? (ag.coluna ? [ag.coluna] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
              <button class="btn-ghost btn-sm" on:click={() => moverAgrupamento(i, -1)} disabled={i === 0}>↑</button>
              <button class="btn-ghost btn-sm" on:click={() => moverAgrupamento(i, 1)} disabled={i === agrupamentos.length - 1}>↓</button>
              <button class="btn-ghost btn-sm danger" on:click={() => removerAgrupamento(i)}>✕</button>
            </div>
          {/each}
        </div>

        <div class="section-block">
          <div class="section-header">
            <span class="section-title">Agregações</span>
            <button class="btn-ghost btn-sm" on:click={adicionarAgregacao}>+ Agregação</button>
          </div>
          {#each agregacoes as ag, i}
            <div class="agreg-row">
              <select bind:value={ag.coluna}>
                <option value="">— coluna —</option>
                {#each resultadoTeste?.colunas ?? (ag.coluna ? [ag.coluna] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
              <select bind:value={ag.funcao}>
                <option value="soma">Soma</option>
                <option value="contagem">Contagem</option>
                <option value="media">Média</option>
                <option value="minimo">Mínimo</option>
                <option value="maximo">Máximo</option>
              </select>
              <input bind:value={ag.label} placeholder="Rótulo (opcional)" />
              <button class="btn-ghost btn-sm danger" on:click={() => removerAgregacao(i)}>✕</button>
            </div>
          {/each}
        </div>

        <div class="section-block">
          <span class="section-title">Subconsulta (drill-down)</span>
          <label class="lbl">
            Query chamada ao clicar em "Ações"
            <select bind:value={form.subquery_id} on:change={onSubqueryChange}>
              <option value={null}>— nenhuma —</option>
              {#each queriesDisponiveis.filter(q => q.slug !== form.slug) as q}
                <option value={q.id}>{q.nome} ({q.tipo})</option>
              {/each}
            </select>
          </label>
          {#if subqueryParams.length > 0}
            <p class="hint-block">Para cada parâmetro da subconsulta, escolha de qual coluna desta query o valor vem:</p>
            {#each subqueryParams as p, i}
              <div class="agrup-row">
                <span class="pos-badge">{p.nome}</span>
                <select bind:value={mapeamentoSubquery[i].coluna_origem}>
                  <option value="">— coluna —</option>
                  {#each resultadoTeste?.colunas ?? (mapeamentoSubquery[i].coluna_origem ? [mapeamentoSubquery[i].coluna_origem] : []) as c}
                    <option value={c}>{c}</option>
                  {/each}
                </select>
              </div>
            {/each}
          {:else if form.subquery_id}
            <p class="hint-block">Essa subconsulta não tem parâmetros cadastrados.</p>
          {/if}
        </div>
      {/if}

      {#if ['chart_bar', 'chart_bar_horizontal', 'chart_line', 'chart_doughnut'].includes(form.tipo)}
        <div class="section-block">
          <span class="section-title">Configurações do Gráfico</span>
          <div class="cores-row">
            <label class="lbl">
              Tamanho da fonte (px)
              <input type="number" bind:value={form.chart_fonte_tamanho} min="8" max="32" style="width:90px" />
            </label>
            <label class="check-inline">
              <input type="checkbox" bind:checked={form.chart_truncar_label} />
              Truncar rótulos
            </label>
            {#if form.chart_truncar_label}
              <label class="lbl">
                Caracteres
                <input type="number" bind:value={form.chart_truncar_tamanho} min="3" max="60" style="width:90px" />
              </label>
            {/if}
            <label class="check-inline">
              <input type="checkbox" bind:checked={form.chart_mostrar_valor} />
              Mostrar valor no gráfico
            </label>
            {#if ['chart_bar', 'chart_bar_horizontal', 'chart_line'].includes(form.tipo)}
              <label class="lbl">
                Nome de exibição do valor principal (opcional)
                <input type="text" bind:value={form.chart_valor_label} placeholder="ex: Perdas" style="width:180px" />
              </label>
            {/if}
            <label class="lbl">
              Coluna com o id bruto pro filtro por clique (opcional)
              <select bind:value={form.chart_filtro_coluna}>
                <option value="">— nenhuma —</option>
                {#each resultadoTeste?.colunas ?? (form.chart_filtro_coluna ? [form.chart_filtro_coluna] : []) as c}
                  <option value={c}>{c}</option>
                {/each}
              </select>
            </label>
          </div>
        </div>
      {/if}

      <!-- Parâmetros -->
      <div class="section-block">
        <div class="section-header">
          <span class="section-title">Parâmetros ($1, $2...)</span>
          <button class="btn-ghost btn-sm" on:click={adicionarParam}>+ Adicionar</button>
        </div>

        {#if params.length === 0}
          <p class="hint-block">Sem parâmetros — o SQL é executado sem filtros posicionais.</p>
        {:else}
          <div class="params-table">
            <div class="params-head">
              <span>Pos.</span>
              <span>Variável do Painel</span>
              <span>Nome / slug</span>
              <span>Obrig.</span>
              <span>Valor Padrão</span>
              <span class="col-teste">Valor de Teste</span>
              <span></span>
            </div>
            {#each params as p, i}
              <div class="params-row">
                <span class="pos-badge">${i + 1}</span>

                <select
                  bind:value={p.variavel_id}
                  on:change={() => onVariavelChange(p, i)}
                >
                  <option value={null}>— manual —</option>
                  {#each variaveis as v}
                    <option value={v.id}>{v.nome} ({v.tipo})</option>
                  {/each}
                </select>

                {#if p.param_slot}
                  <span class="slot-badge slot-{p.param_slot}">{p.param_slot === 'inicio' ? 'Início' : 'Fim'}</span>
                {:else}
                  <input
                    bind:value={p.nome}
                    placeholder="slug_param"
                    readonly={!!p.variavel_id}
                    style={p.variavel_id ? 'opacity:.5;cursor:default' : ''}
                  />
                {/if}

                <input type="checkbox" bind:checked={p.obrigatorio} style="margin:auto" />
                <input bind:value={p.valor_padrao} placeholder="padrão" />
                <input class="input-teste" bind:value={p._testar_valor} placeholder="valor p/ teste" />
                <button class="btn-ghost btn-sm danger" on:click={() => removerParam(i)}>✕</button>
              </div>
            {/each}
          </div>
          <p class="hint-block">
            Vincule cada <code>$N</code> a uma variável do painel. Ao renderizar, o valor do filtro selecionado pelo usuário será passado na posição correspondente.
            "Valor de Teste" é usado apenas ao clicar em Testar.<br>
            <strong>Tokens para Valor Padrão:</strong>
            <code>mes_atual_inicio</code> · <code>mes_atual_fim</code> ·
            <code>mes_anterior_inicio</code> · <code>mes_anterior_fim</code> ·
            <code>ano_atual_inicio</code> · <code>ano_atual_fim</code> ·
            <code>hoje</code> · <code>ontem</code>
          </p>
          <p class="hint-block">
            <strong>Exemplo — variável Multi-seleção (multiselect):</strong><br>
            1. Adicione <code>$N</code> no SQL: <code>AND ($N::text IS NULL OR coluna = ANY(string_to_array($N, ',')::tipo[]))</code> — troque <code>tipo</code> por <code>bigint</code>/<code>int</code>/nada (se for texto, remova o <code>::tipo[]</code>).
          </p>
          <p class="hint-block">
            <strong>Exemplo — variável Seleção (dropdown, valor único):</strong><br>
            Adicione <code>$N</code> no SQL: <code>AND ($N::text IS NULL OR coluna = $N)</code> — sem <code>string_to_array</code>, pois só um valor é selecionado por vez.
          </p>
          <p class="hint-block">
            <strong>Filtro automático por usuário (<code>codigo_usuario_externo</code>):</strong><br>
            Adicione um parâmetro <strong>manual</strong> (sem Variável do Painel vinculada) com o nome exato <code>codigo_usuario_externo</code>, na posição <code>$N</code> onde quiser usá-lo no SQL — ex: <code>WHERE usuario_id = $N</code>. O backend preenche esse valor sozinho (código do usuário da sessão SSO, ou o código vinculado ao usuário em Configurações → Usuários) e sempre ignora qualquer valor vindo da tela. Não expõe filtro nenhum pro usuário — fica invisível.
          </p>
        {/if}
      </div>

      <!-- SQL -->
      <div style="border-top:1px solid var(--border); padding-top:16px;">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">
          <p style="font-size:13px; color:var(--muted); margin:0;">SQL da Query</p>
          <label style="display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted);">
            Testar na empresa:
            <select bind:value={testarEmpresaId} style="font-size:12px; padding:4px 8px;">
              {#each empresas as e}
                <option value={e.id}>{e.nome}</option>
              {/each}
            </select>
          </label>
        </div>
        <QueryEditor
          bind:sql={form.sql_texto}
          tipo={form.tipo}
          onTestar={testar}
        />
      </div>

      {#if erro}<p class="error">{erro}</p>{/if}

      <button class="btn-primary" on:click={salvar} disabled={salvando}>
        {salvando ? 'Salvando...' : 'Salvar Alterações'}
      </button>
    </div>
  {/if}
</div>

<style>
.lbl { display:flex; flex-direction:column; gap:6px; font-size:13px; color:var(--muted); }
.check-inline { display:flex; align-items:center; gap:6px; font-size:13px; color:var(--text); cursor:pointer; text-transform:none; letter-spacing:0; font-weight:400; }

.section-block { border:1px solid var(--border); border-radius:6px; padding:14px; display:flex; flex-direction:column; gap:10px; }
.section-header { display:flex; justify-content:space-between; align-items:center; }
.section-title { font-size:12px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }

.params-table { display:flex; flex-direction:column; gap:6px; }
.params-head { display:grid; grid-template-columns:40px 1.4fr 1fr 50px 1fr 1fr 32px; gap:6px; font-size:11px; color:var(--muted); text-transform:uppercase; padding:0 2px; }
.params-row  { display:grid; grid-template-columns:40px 1.4fr 1fr 50px 1fr 1fr 32px; gap:6px; align-items:center; }

.pos-badge { font-size:12px; font-family:var(--font-display); color:var(--accent-blue); text-align:center; }
.input-teste { background:color-mix(in srgb, var(--accent-blue) 8%, var(--surface2)); border-color:color-mix(in srgb, var(--accent-blue) 30%, var(--border)); }

.hint-block { font-size:12px; color:var(--muted); }
.col-teste { color:var(--accent-blue) !important; }
.kpi-cores { border:1px solid var(--border); border-radius:6px; padding:14px; display:flex; flex-direction:column; gap:10px; }
.cores-row { display:flex; gap:20px; align-items:flex-end; flex-wrap:wrap; }
.color-pick { display:flex; align-items:center; gap:6px; }
.color-pick input[type="color"] { width:36px; height:32px; padding:2px; border-radius:4px; border:1px solid var(--border); background:none; cursor:pointer; }
.kpi-preview { border-radius:6px; padding:12px 16px; display:flex; flex-direction:column; gap:4px; min-width:120px; border:1px solid transparent; }
.kpi-preview-label { font-size:11px; text-transform:uppercase; letter-spacing:.06em; }
.kpi-preview-valor { font-size:24px; font-weight:500; font-family:var(--font-display); }
.kpi-imagem-preview { width:56px; height:56px; object-fit:contain; border-radius:6px; border:1px solid var(--border); }
.slot-badge { font-size:11px; font-weight:600; padding:2px 8px; border-radius:4px; white-space:nowrap; }
.slot-inicio { background:color-mix(in srgb,#3fb950 15%,var(--surface2)); color:#3fb950; }
.slot-fim    { background:color-mix(in srgb,#f85149 15%,var(--surface2)); color:#f85149; }
.error  { color:var(--danger, #f85149); font-size:13px; }
.danger { color:var(--danger, #f85149); }
.btn-sm { font-size:12px; padding:4px 8px; }
.agrup-row { display: grid; grid-template-columns: 90px 1fr 32px 32px 32px; gap: 6px; align-items: center; }
.agreg-row { display: grid; grid-template-columns: 1fr 1fr 1fr 32px; gap: 6px; align-items: center; }
</style>
