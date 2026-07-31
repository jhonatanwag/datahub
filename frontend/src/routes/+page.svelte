<script>
  import { api, assetUrl } from '$lib/api.js';

  const carregarPaineis = api.meuDashboard();
</script>

<svelte:head><title>Dashboard — GPA Analytics</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Meus Painéis</h2>
  </div>

  {#await carregarPaineis}
    <div class="grid">
      {#each Array(6) as _}
        <div class="card skeleton"></div>
      {/each}
    </div>

  {:then paineis}
    {#if paineis.length === 0}
      <div class="empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
          <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
        </svg>
        <p>Nenhum painel disponível para esta empresa.</p>
      </div>
    {:else}
      <div class="grid">
        {#each paineis as p}
          <div class="card painel-card">
            <div class="card-body">
              <div class="card-text">
                <h3 class="painel-nome">{p.nome}</h3>
                {#if p.descricao}
                  <p class="painel-desc">{p.descricao}</p>
                {/if}
                <span class="badge-ind">
                  {p.total_indicadores} {p.total_indicadores === 1 ? 'indicador' : 'indicadores'}
                </span>
              </div>
              {#if p.imagem_url}
                <img
                  class="painel-imagem"
                  src={assetUrl(p.imagem_url)}
                  alt={p.nome}
                  on:error={(e) => { e.target.style.display = 'none'; }}
                />
              {/if}
            </div>
            <div class="card-footer">
              <a href="/painel/{p.slug}" class="btn-primary btn-sm">Ver painel →</a>
            </div>
          </div>
        {/each}
      </div>
    {/if}

  {:catch erro}
    <p class="error">Erro ao carregar painéis: {erro.message}</p>
  {/await}
</div>

<style>
.page        { padding: 24px; }
.page-header { margin-bottom: 24px; }
h2           { font-size: 20px; color: var(--text); font-family: var(--font-display); }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.painel-card {
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

.card-body   { padding: 20px 20px 14px; display: flex; flex-direction: row; align-items: stretch; gap: 12px; flex: 1; }
.card-text   { display: flex; flex-direction: column; gap: 8px; flex: 1; min-width: 0; }
.painel-imagem { width: 96px; flex-shrink: 0; align-self: center; object-fit: contain; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; }
.card-footer { padding: 12px 20px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; }

.painel-nome { font-size: 15px; font-weight: 600; color: var(--text); font-family: var(--font-display); }
.painel-desc { font-size: 13px; color: var(--muted); line-height: 1.5; }

.badge-ind {
  display: inline-block;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 20px;
  background: var(--surface2);
  color: var(--muted);
  width: fit-content;
}

.btn-sm { font-size: 13px; padding: 6px 14px; border-radius: 20px; }

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 60px 0;
  color: var(--muted);
}
.empty svg { width: 48px; height: 48px; opacity: .3; }
.empty p   { font-size: 14px; }

@keyframes pulse { 0%,100%{opacity:.4} 50%{opacity:.8} }
.skeleton { height: 130px; animation: pulse 1.5s infinite; }
</style>
