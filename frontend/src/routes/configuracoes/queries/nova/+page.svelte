<script>
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';
  import QueryEditor from '$lib/components/QueryEditor.svelte';

  let form = {
    slug: '', nome: '', descricao: '',
    sql_texto: '', tipo: 'kpi',
    empresa_id: null, cache_ttl: 300, ativo: true,
    kpi_cor_fonte: '#e6edf3', kpi_cor_fundo: '#161b22',
    mapa_camada: 'padrao',
    chart_fonte_tamanho: 12, chart_truncar_label: false,
    chart_truncar_tamanho: 15, chart_mostrar_valor: false,
    chart_valor_label: ''
  };

  // cada item: { nome, tipo, obrigatorio, valor_padrao, descricao, variavel_id, _testar_valor }
  let params          = [];
  let testarEmpresaId = null;
  let empresas        = [];
  let variaveis       = [];
  let resultadoTeste  = null;
  let salvando        = false;
  let erro            = null;

  const tipos = [
    'kpi', 'chart_line', 'chart_bar',
    'chart_bar_horizontal', 'chart_doughnut',
    'table', 'rag_context', 'map'
  ];

  onMount(async () => {
    try {
      const [emps, vars] = await Promise.all([
        api.listarEmpresas(),
        api.listarVariaveis(),
      ]);
      empresas  = emps;
      variaveis = vars.filter(v => v.ativo);
      if (emps.length > 0) testarEmpresaId = emps[0].id;
    } catch (e) {
      console.error('Erro ao carregar dados:', e);
    }
  });

  // Quando variavel_id muda, preenche nome/tipo e expande date_range em dois slots
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
      // Substitui a linha atual por duas: inicio e fim
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
    if (!form.slug.trim()) {
      erro = 'Slug é obrigatório.';
      return;
    }
    if (!form.nome.trim()) {
      erro = 'Nome legível é obrigatório.';
      return;
    }
    if (!resultadoTeste?.ok) {
      erro = 'Teste a query antes de salvar.';
      return;
    }
    erro = null;
    salvando = true;
    try {
      const q = await api.criarQuery(form);
      if (params.length > 0) {
        await api.salvarParametrosQuery(q.id, params.map(({ _testar_valor, ...p }) => p));
      }
      goto('/configuracoes/queries');
    } catch (e) {
      erro = e.message;
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Nova Query — DataHub</title></svelte:head>

<div style="padding:24px; max-width:860px; margin:0 auto;">
  <div style="display:flex; align-items:center; gap:16px; margin-bottom:24px;">
    <a href="/configuracoes/queries" style="color:var(--muted)">← Voltar</a>
    <h2 style="font-family:var(--font-display)">Nova Query</h2>
  </div>

  <div class="card" style="display:flex; flex-direction:column; gap:16px;">
    <!-- Identificação -->
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
      <label class="lbl">
        Slug (identificador único)
        <input bind:value={form.slug} placeholder="ex: kpi_receita" />
      </label>
      <label class="lbl">
        Nome legível
        <input bind:value={form.nome} placeholder="ex: Receita Total (30d)" />
      </label>
    </div>

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
          </label>
          <label class="lbl">
            Cor de fundo
            <div class="color-pick">
              <input type="color" bind:value={form.kpi_cor_fundo} />
              <input type="text"  bind:value={form.kpi_cor_fundo} placeholder="#161b22" style="width:90px" />
            </div>
          </label>
          <div class="kpi-preview" style="background:{form.kpi_cor_fundo}; color:{form.kpi_cor_fonte}">
            <span class="kpi-preview-label" style="color:{form.kpi_cor_fonte}; opacity:.7">LABEL</span>
            <span class="kpi-preview-valor" style="color:{form.kpi_cor_fonte}">1.234</span>
          </div>
        </div>
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

              <!-- Dropdown da variável vinculada -->
              <select
                bind:value={p.variavel_id}
                on:change={() => onVariavelChange(p, i)}
              >
                <option value={null}>— manual —</option>
                {#each variaveis as v}
                  <option value={v.id}>{v.nome} ({v.tipo})</option>
                {/each}
              </select>

              <!-- Nome / slot (readonly se vinculado a variável) -->
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

    <button class="btn-primary" on:click={salvar} disabled={salvando || !resultadoTeste?.ok}>
      {salvando ? 'Salvando...' : 'Salvar Query'}
    </button>
  </div>
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
.slot-badge { font-size:11px; font-weight:600; padding:2px 8px; border-radius:4px; white-space:nowrap; }
.slot-inicio { background:color-mix(in srgb,#3fb950 15%,var(--surface2)); color:#3fb950; }
.slot-fim    { background:color-mix(in srgb,#f85149 15%,var(--surface2)); color:#f85149; }
.error  { color:var(--danger, #f85149); font-size:13px; }
.danger { color:var(--danger, #f85149); }
.btn-sm { font-size:12px; padding:4px 8px; }
</style>
