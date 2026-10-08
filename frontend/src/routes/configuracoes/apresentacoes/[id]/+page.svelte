<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';
  import { chavesFiltro } from '$lib/filtrosPainel.js';

  const idParam = $page.params.id;
  const criando = idParam === 'nova';

  let form = { slug: '', nome: '', descricao: '', empresa_id: null, intervalo_min: 5, ativo: true };
  let slides = [];            // [{ chave, painel_id, duracao_seg, filtros, variaveis, painel_ativo }]
  let paineis = [];
  let empresas = [];
  let usuarios = [];
  let usuariosSelecionados = [];
  let carregando = true, salvando = false, erro = null;
  let proximaChave = 1;

  onMount(async () => {
    try {
      [paineis, empresas, usuarios] = await Promise.all([
        api.listarPaineis(), api.listarEmpresas(), api.listarUsuarios(),
      ]);
      if (!criando) {
        const [a, sl, us] = await Promise.all([
          api.buscarApresentacao(idParam), api.slidesApresentacao(idParam), api.usuariosApresentacao(idParam),
        ]);
        form = {
          slug: a.slug, nome: a.nome, descricao: a.descricao ?? '', empresa_id: a.empresa_id,
          intervalo_min: Math.max(0.5, a.intervalo_atualizacao_seg / 60), ativo: a.ativo,
        };
        usuariosSelecionados = us.map(u => u.id);
        slides = await Promise.all(sl.map(async s => ({
          chave: proximaChave++, painel_id: s.painel_id, duracao_seg: s.duracao_seg,
          filtros: { ...s.filtros }, painel_ativo: s.painel_ativo,
          variaveis: await api.variaveisPainel(s.painel_id).catch(() => []),
        })));
      }
    } catch (e) { erro = e.message; }
    finally { carregando = false; }
  });

  // Valores padrão do painel (tokens crus) viram os filtros iniciais do slide.
  function filtrosPadrao(variaveis) {
    const f = {};
    for (const v of variaveis) {
      if (v.tipo === 'date_range') {
        f[v.slug + '_inicio'] = v.valor_padrao_inicio || '';
        f[v.slug + '_fim'] = v.valor_padrao_fim || '';
      } else {
        f[v.slug] = v.valor_padrao || '';
      }
    }
    return f;
  }

  function adicionarSlide() {
    slides = [...slides, {
      chave: proximaChave++, painel_id: null, duracao_seg: 30,
      filtros: {}, variaveis: [], painel_ativo: true,
    }];
  }

  async function trocarPainel(s, painelId) {
    s.painel_id = painelId ? Number(painelId) : null;
    s.painel_ativo = true;
    s.variaveis = s.painel_id ? await api.variaveisPainel(s.painel_id).catch(() => []) : [];
    s.filtros = filtrosPadrao(s.variaveis);
    slides = slides;
  }

  function mover(i, delta) {
    const j = i + delta;
    if (j < 0 || j >= slides.length) return;
    const c = [...slides];
    [c[i], c[j]] = [c[j], c[i]];
    slides = c;
  }

  function remover(i) { slides = slides.filter((_, k) => k !== i); }

  function toggleUsuario(uid) {
    usuariosSelecionados = usuariosSelecionados.includes(uid)
      ? usuariosSelecionados.filter(x => x !== uid)
      : [...usuariosSelecionados, uid];
  }

  function normalizarSlug(e) {
    form.slug = e.target.value.toLowerCase().replace(/[\s-]+/g, '_').replace(/[^a-z0-9_]/g, '');
  }

  async function salvar() {
    erro = null;
    if (!form.nome.trim() || !form.slug.trim()) { erro = 'Informe nome e slug.'; return; }
    if (slides.some(s => !s.painel_id)) { erro = 'Escolha o painel de todos os slides (ou remova o slide vazio).'; return; }
    salvando = true;
    try {
      const corpo = {
        slug: form.slug.trim(), nome: form.nome.trim(), descricao: form.descricao || null,
        empresa_id: form.empresa_id || null,
        intervalo_atualizacao_seg: Math.round(Number(form.intervalo_min) * 60), ativo: form.ativo,
      };
      const id = criando ? (await api.criarApresentacao(corpo)).id : idParam;
      if (!criando) await api.atualizarApresentacao(id, corpo);
      await api.salvarSlidesApresentacao(id, slides.map(s => ({
        painel_id: s.painel_id, duracao_seg: Number(s.duracao_seg), filtros: s.filtros,
      })));
      await api.salvarUsuariosApresentacao(id, usuariosSelecionados);
      goto('/configuracoes/apresentacoes');
    } catch (e) { erro = e.message; }
    finally { salvando = false; }
  }
</script>

<svelte:head><title>{criando ? 'Nova apresentação' : 'Editar apresentação'} — GPA Analytics</title></svelte:head>

<div class="page">
  <div class="page-header">
    <a href="/configuracoes/apresentacoes" class="voltar">← Apresentações</a>
    <h2>{criando ? 'Nova apresentação' : 'Editar apresentação'}</h2>
  </div>

  {#if carregando}
    <p class="muted">Carregando...</p>
  {:else}
    <div class="form-card">
      <div class="section-title">Dados</div>
      <div class="field-row">
        <div class="field flex-1">
          <label for="ap-nome">Nome</label>
          <input id="ap-nome" type="text" bind:value={form.nome} placeholder="TV Produção" />
        </div>
        <div class="field flex-1">
          <label for="ap-slug">Slug</label>
          <input id="ap-slug" type="text" value={form.slug} on:input={normalizarSlug} placeholder="tv_producao" />
        </div>
      </div>
      <div class="field">
        <label for="ap-desc">Descrição</label>
        <input id="ap-desc" type="text" bind:value={form.descricao} />
      </div>
      <div class="field-row">
        <div class="field flex-1">
          <label for="ap-emp">Empresa</label>
          <select id="ap-emp" bind:value={form.empresa_id}>
            <option value={null}>Todas as empresas</option>
            {#each empresas as e}<option value={e.id}>{e.nome}</option>{/each}
          </select>
        </div>
        <div class="field flex-1">
          <label for="ap-int">Atualizar dados a cada (minutos)</label>
          <input id="ap-int" type="number" min="0.5" step="0.5" bind:value={form.intervalo_min} />
        </div>
      </div>
      <label class="check-label"><input type="checkbox" bind:checked={form.ativo} /> Ativa</label>
    </div>

    <div class="form-card bloco">
      <div class="section-title">Slides</div>
      <span class="hint">Cada slide é um painel já cadastrado. O tempo é o mínimo na tela: se o painel for mais alto que a tela, ele rola sozinho e o slide só passa quando a rolagem termina.</span>

      {#each slides as s, i (s.chave)}
        <div class="slide">
          <div class="slide-topo">
            <strong>Slide {i + 1}</strong>
            <div class="slide-acoes">
              <button type="button" class="btn-ghost btn-sm" on:click={() => mover(i, -1)} disabled={i === 0} title="Mover para cima">↑</button>
              <button type="button" class="btn-ghost btn-sm" on:click={() => mover(i, 1)} disabled={i === slides.length - 1} title="Mover para baixo">↓</button>
              <button type="button" class="btn-ghost btn-sm danger" on:click={() => remover(i)} title="Remover slide">✕</button>
            </div>
          </div>

          <div class="field-row">
            <div class="field flex-1">
              <label for="sl-painel-{s.chave}">Painel</label>
              <select id="sl-painel-{s.chave}" value={s.painel_id ?? ''} on:change={(e) => trocarPainel(s, e.target.value)}>
                <option value="">— escolha um painel —</option>
                {#each paineis.filter(p => p.ativo || p.id === s.painel_id) as p}
                  <option value={p.id}>{p.nome}{p.ativo ? '' : ' (inativo)'}</option>
                {/each}
              </select>
            </div>
            <div class="field">
              <label for="sl-dur-{s.chave}">Tempo na tela (segundos)</label>
              <input id="sl-dur-{s.chave}" type="number" min="5" bind:value={s.duracao_seg} />
            </div>
          </div>

          {#if s.painel_id && !s.painel_ativo}
            <span class="aviso">Painel inativo: este slide será pulado na apresentação.</span>
          {/if}

          {#if s.variaveis.length > 0}
            <div class="filtros-slide">
              <span class="hint">Filtros fixos deste slide (valor ou token: hoje, ontem, mes_atual_inicio, mes_atual_fim, mes_anterior_inicio, mes_anterior_fim, ano_atual_inicio, ano_atual_fim). Quem apresenta pode alterá-los antes de iniciar.</span>
              {#each s.variaveis as v}
                {#each chavesFiltro(v) as c}
                  <div class="field">
                    <label for="sl-f-{s.chave}-{c.chave}">{c.rotulo}</label>
                    <input id="sl-f-{s.chave}-{c.chave}" type="text" bind:value={s.filtros[c.chave]} placeholder="vazio = sem filtro" />
                  </div>
                {/each}
              {/each}
            </div>
          {/if}
        </div>
      {:else}
        <p class="muted">Nenhum slide ainda.</p>
      {/each}

      <div><button type="button" class="btn-ghost" on:click={adicionarSlide}>+ Adicionar slide</button></div>
    </div>

    <div class="form-card bloco">
      <div class="section-title">Usuários com acesso</div>
      <span class="hint">Administradores sempre enxergam todas as apresentações da empresa.</span>
      {#each usuarios as u}
        <div class="access-row">
          <label class="check-label">
            <input type="checkbox" checked={usuariosSelecionados.includes(u.id)} on:change={() => toggleUsuario(u.id)} />
            <span>{u.nome}</span>
            <span class="badge">{u.role}</span>
            <span class="hint">{u.email}</span>
          </label>
        </div>
      {/each}
    </div>

    {#if erro}<p class="error">{erro}</p>{/if}
    <div class="rodape">
      <a href="/configuracoes/apresentacoes" class="btn-ghost">Cancelar</a>
      <button class="btn-primary" on:click={salvar} disabled={salvando}>{salvando ? 'Salvando…' : 'Salvar'}</button>
    </div>
  {/if}
</div>

<style>
.page { padding: 24px; max-width: 960px; }
.page-header { margin-bottom: 20px; }
.voltar { font-size: 12px; color: var(--muted); text-decoration: none; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); margin-top: 4px; }
.form-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.bloco { margin-top: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field.flex-1 { flex: 1; }
.field-row { display: flex; gap: 16px; flex-wrap: wrap; }
.check-label { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); cursor: pointer; }
.hint { font-size: 11px; color: var(--muted); }
.section-title { font-size: 12px; color: var(--muted); font-weight: 600; letter-spacing: .06em; }
.access-row { padding: 8px 0; border-bottom: 1px solid var(--border); }
.badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; background: var(--surface2); color: var(--muted); }
.slide { border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; display: flex; flex-direction: column; gap: 12px; background: var(--surface2); }
.slide-topo { display: flex; justify-content: space-between; align-items: center; color: var(--text); }
.slide-acoes { display: flex; gap: 6px; }
.filtros-slide { display: flex; flex-direction: column; gap: 10px; }
.aviso { color: var(--accent-orange); font-size: 12px; }
.btn-sm { font-size: 12px; padding: 4px 10px; }
.danger { color: var(--danger, #f85149); }
.rodape { display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; }
.muted { color: var(--muted); }
.error { color: var(--danger, #f85149); font-size: 13px; margin-top: 12px; }
input[type="text"], input[type="number"], select { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text); font-size: 13px; }
</style>
