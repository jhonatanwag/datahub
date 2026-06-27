<script>
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let abaAtiva = 'geral';

  let form = {
    slug: '', nome: '', descricao: '', icone: 'chart-bar',
    colunas: 3, linhas_fixas: false, total_linhas: null,
    empresa_id: null, ativo: true, ordem_menu: 0
  };

  let indicadores        = [];
  let varSelecionadas    = [];
  let usuariosSelecionados = [];

  let queries    = [];
  let variaveis  = [];
  let usuarios   = [];
  let empresas   = [];
  let carregando = true;
  let salvando   = false;
  let erro       = null;

  onMount(async () => {
    try {
      [queries, variaveis, usuarios, empresas] = await Promise.all([
        api.listarQueries(),
        api.listarVariaveis(),
        api.listarUsuarios(),
        api.listarEmpresas(),
      ]);
    } catch (e) {
      erro = e.message;
    } finally {
      carregando = false;
    }
  });

  function gerarSlug(nome) {
    return nome.toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
  }

  function adicionarIndicador() {
    indicadores = [...indicadores, {
      query_slug: queries[0]?.slug || '', titulo: '',
      linha: indicadores.length + 1, coluna: 1,
      col_span: 1, row_span: 1, posicao: indicadores.length
    }];
  }

  function removerIndicador(i) {
    indicadores = indicadores.filter((_, idx) => idx !== i);
  }

  function toggleVariavel(v) {
    const idx = varSelecionadas.findIndex(s => s.variavel_id === v.id);
    if (idx >= 0) {
      varSelecionadas = varSelecionadas.filter((_, i) => i !== idx);
    } else {
      varSelecionadas = [...varSelecionadas, {
        variavel_id: v.id, obrigatorio: false, valor_padrao: '', posicao: varSelecionadas.length
      }];
    }
  }

  function isVarSelecionada(id) {
    return varSelecionadas.some(s => s.variavel_id === id);
  }

  function toggleUsuario(id) {
    if (usuariosSelecionados.includes(id)) {
      usuariosSelecionados = usuariosSelecionados.filter(x => x !== id);
    } else {
      usuariosSelecionados = [...usuariosSelecionados, id];
    }
  }

  async function salvar() {
    if (!form.nome) { erro = 'Nome é obrigatório.'; return; }
    if (!form.slug) { form.slug = gerarSlug(form.nome); }
    erro = null;
    salvando = true;
    try {
      const painel = await api.criarPainel(form);
      if (indicadores.length > 0) {
        await api.salvarIndicadores(painel.id, indicadores);
      }
      if (varSelecionadas.length > 0) {
        await api.salvarVariaveisPainel(painel.id, varSelecionadas);
      }
      if (usuariosSelecionados.length > 0) {
        await api.salvarUsuariosPainel(painel.id, usuariosSelecionados);
      }
      goto('/configuracoes/paineis');
    } catch (e) {
      erro = e.message;
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Novo Painel — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <a href="/configuracoes/paineis" class="back-link">← Voltar</a>
    <h2>Novo Painel</h2>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else}
    <div class="tabs">
      <button class="tab" class:active={abaAtiva === 'geral'} on:click={() => abaAtiva = 'geral'}>
        Configurações Gerais
      </button>
      <button class="tab" class:active={abaAtiva === 'indicadores'} on:click={() => abaAtiva = 'indicadores'}>
        Indicadores ({indicadores.length})
      </button>
      <button class="tab" class:active={abaAtiva === 'acesso'} on:click={() => abaAtiva = 'acesso'}>
        Filtros e Acesso
      </button>
    </div>

    {#if abaAtiva === 'geral'}
      <div class="form-card">
        <div class="field">
          <label>Nome do Painel</label>
          <input type="text" bind:value={form.nome}
            on:input={() => { if (!form.slug) form.slug = gerarSlug(form.nome); }}
            placeholder="ex: Visão Geral" />
        </div>
        <div class="field">
          <label>Slug</label>
          <input type="text" bind:value={form.slug} placeholder="ex: visao_geral" />
        </div>
        <div class="field">
          <label>Ícone</label>
          <input type="text" bind:value={form.icone} placeholder="chart-bar" />
          <span class="hint">Nome do ícone (usado no menu lateral)</span>
        </div>
        <div class="field">
          <label>Descrição</label>
          <input type="text" bind:value={form.descricao} placeholder="Opcional" />
        </div>
        <div class="field">
          <label>Empresa</label>
          <select bind:value={form.empresa_id}>
            <option value={null}>Global (todas as empresas)</option>
            {#each empresas as e}
              <option value={e.id}>{e.nome} ({e.slug})</option>
            {/each}
          </select>
        </div>
        <div class="field-row">
          <div class="field">
            <label>Colunas do Grid</label>
            <input type="number" bind:value={form.colunas} min="1" max="12" />
          </div>
          <div class="field">
            <label>Ordem no Menu</label>
            <input type="number" bind:value={form.ordem_menu} min="0" />
          </div>
        </div>
        <div class="field">
          <label>Linhas</label>
          <div class="radio-group">
            <label class="radio-label">
              <input type="radio" bind:group={form.linhas_fixas} value={false} /> Contínuas
            </label>
            <label class="radio-label">
              <input type="radio" bind:group={form.linhas_fixas} value={true} /> Fixas
              {#if form.linhas_fixas}
                <input type="number" bind:value={form.total_linhas} min="1" style="width:60px; margin-left:8px" />
              {/if}
            </label>
          </div>
        </div>
      </div>
    {/if}

    {#if abaAtiva === 'indicadores'}
      <div class="form-card">
        <div class="ind-layout">
          <div class="ind-editor">
            <button class="btn-ghost" on:click={adicionarIndicador}>+ Adicionar Indicador</button>
            {#if indicadores.length === 0}
              <p class="muted" style="margin-top:16px">Nenhum indicador adicionado.</p>
            {:else}
              {#each indicadores as ind, i}
                <div class="ind-item">
                  <div class="ind-row">
                    <div class="field flex-1">
                      <label>Query</label>
                      <select bind:value={ind.query_slug}>
                        {#each queries as q}
                          <option value={q.slug}>{q.nome} ({q.tipo})</option>
                        {/each}
                      </select>
                    </div>
                    <button class="btn-ghost btn-sm danger" on:click={() => removerIndicador(i)}>✕</button>
                  </div>
                  <div class="field">
                    <label>Título (opcional)</label>
                    <input type="text" bind:value={ind.titulo} placeholder="Override do título" />
                  </div>
                  <div class="grid-4">
                    <div class="field">
                      <label>Linha</label>
                      <input type="number" bind:value={ind.linha} min="1" />
                    </div>
                    <div class="field">
                      <label>Coluna</label>
                      <input type="number" bind:value={ind.coluna} min="1" />
                    </div>
                    <div class="field">
                      <label>Col Span</label>
                      <input type="number" bind:value={ind.col_span} min="1" max={form.colunas} />
                    </div>
                    <div class="field">
                      <label>Row Span</label>
                      <input type="number" bind:value={ind.row_span} min="1" />
                    </div>
                  </div>
                </div>
              {/each}
            {/if}
          </div>

          <div class="ind-preview">
            <div class="preview-label">Preview ({form.colunas} colunas)</div>
            <div class="preview-grid" style="grid-template-columns: repeat({form.colunas}, 1fr)">
              {#each indicadores as ind}
                <div class="preview-cell"
                  style="grid-column: {ind.coluna} / span {ind.col_span}; grid-row: {ind.linha} / span {ind.row_span}">
                  <span class="preview-slug">{ind.titulo || ind.query_slug}</span>
                </div>
              {/each}
            </div>
          </div>
        </div>
      </div>
    {/if}

    {#if abaAtiva === 'acesso'}
      <div class="form-card">
        <div class="section-title">Variáveis de Filtro</div>
        {#each variaveis as v}
          <div class="access-row">
            <label class="check-label">
              <input type="checkbox"
                checked={isVarSelecionada(v.id)}
                on:change={() => toggleVariavel(v)}
              />
              <span>{v.nome}</span>
              <span class="badge">{v.tipo}</span>
            </label>
            {#if isVarSelecionada(v.id)}
              {@const sel = varSelecionadas.find(s => s.variavel_id === v.id)}
              <label class="check-label sub">
                <input type="checkbox" bind:checked={sel.obrigatorio} /> Obrigatório
              </label>
              <div class="sub-row">
                <span class="hint">Valor padrão:</span>
                <input type="text" bind:value={sel.valor_padrao} style="width:140px" />
              </div>
            {/if}
          </div>
        {/each}

        <div class="section-title" style="margin-top:24px">Usuários com Acesso</div>
        {#each usuarios as u}
          <div class="access-row">
            <label class="check-label">
              <input type="checkbox"
                checked={usuariosSelecionados.includes(u.id)}
                on:change={() => toggleUsuario(u.id)}
              />
              <span>{u.nome}</span>
              <span class="badge">{u.role}</span>
              <span class="hint">{u.email}</span>
            </label>
          </div>
        {/each}
      </div>
    {/if}

    {#if erro}
      <p class="error" style="margin-top:16px">{erro}</p>
    {/if}

    <div class="form-footer">
      <a href="/configuracoes/paineis" class="btn-ghost">Cancelar</a>
      <button class="btn-primary" on:click={salvar} disabled={salvando}>
        {salvando ? 'Salvando...' : 'Salvar Painel'}
      </button>
    </div>
  {/if}
</div>

<style>
.page { padding: 24px; max-width: 960px; }
.page-header { margin-bottom: 20px; }
.back-link { color: var(--muted); font-size: 13px; display: block; margin-bottom: 8px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }

.tabs { display: flex; gap: 2px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
.tab { background: none; border: none; padding: 10px 16px; color: var(--muted); font-size: 13px; cursor: pointer; border-bottom: 2px solid transparent; }
.tab.active { color: var(--text); border-bottom-color: var(--accent-blue); }
.tab:hover { color: var(--text); }

.form-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field.flex-1 { flex: 1; }
label { font-size: 12px; color: var(--muted); font-weight: 500; text-transform: uppercase; letter-spacing: .05em; }
input, select { background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text); font-size: 13px; }
.field-row { display: flex; gap: 16px; }
.radio-group { display: flex; gap: 16px; align-items: center; }
.radio-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text); text-transform: none; letter-spacing: 0; font-weight: 400; cursor: pointer; }
.hint { font-size: 11px; color: var(--muted); }

.ind-layout { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.ind-editor { display: flex; flex-direction: column; gap: 12px; }
.ind-item { border: 1px solid var(--border); border-radius: 6px; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.ind-row { display: flex; align-items: flex-end; gap: 8px; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.preview-label { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.preview-grid { display: grid; gap: 4px; min-height: 200px; }
.preview-cell { background: var(--surface2); border: 1px solid var(--border); border-radius: 4px; padding: 8px; display: flex; align-items: center; justify-content: center; min-height: 48px; }
.preview-slug { font-size: 11px; color: var(--muted); text-align: center; word-break: break-all; }

.section-title { font-size: 12px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 8px; }
.access-row { padding: 8px 0; border-bottom: 1px solid var(--border); }
.check-label { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); cursor: pointer; text-transform: none; letter-spacing: 0; font-weight: 400; }
.check-label.sub { margin-left: 32px; font-size: 12px; margin-top: 4px; }
.sub-row { margin-left: 32px; display: flex; gap: 8px; align-items: center; margin-top: 4px; font-size: 12px; }
.badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }

.form-footer { display: flex; gap: 12px; justify-content: flex-end; margin-top: 20px; }
.danger { color: var(--danger, #f85149); }
.btn-sm { font-size: 12px; padding: 4px 10px; }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; }
</style>
