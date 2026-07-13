<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let empresa     = null;
  let logoFile    = null;
  let logoPreview = null;
  let testeStatus   = null; // null | 'ok' | 'fail'
  let testeMensagem = '';
  let testando  = false;
  let salvando  = false;
  let erro      = '';
  let slugErro  = '';

  let ssoApiKeyGerada = null;   // texto puro, só existe em memória após gerar
  let ssoGerando = false;
  let ssoTesteCodigoUsuario = '';
  let ssoTesteStatus = null;    // null | 'ok' | 'fail'
  let ssoTesteResultado = '';
  let ssoTestando = false;

  onMount(async () => {
    try {
      empresa = await api.buscarEmpresa(Number($page.params.id));
    } catch {
      goto('/configuracoes/empresas');
    }
  });

  function validarSlug() {
    if (!empresa?.slug) {
      slugErro = '';
      return;
    }
    if (/\s/.test(empresa.slug)) {
      slugErro = 'Slug não pode conter espaços.';
    } else if (!/^[a-z0-9-]+$/.test(empresa.slug)) {
      slugErro = 'Slug deve conter apenas letras minúsculas, números e hífens.';
    } else {
      slugErro = '';
    }
  }

  function onLogoChange(e) {
    logoFile = e.target.files[0];
    if (logoFile) {
      logoPreview = URL.createObjectURL(logoFile);
    }
  }

  async function testarConexao() {
    testando = true;
    testeStatus = null;
    try {
      const res = await api.testarConexao({
        host: empresa.db_host,
        port: empresa.db_port,
        database: empresa.db_name,
        user: empresa.db_user,
        password: empresa.db_pass
      });
      testeStatus = res.ok ? 'ok' : 'fail';
      testeMensagem = res.ok
        ? (res.tabelas != null ? `Conexão OK — ${res.tabelas} tabelas` : 'Conexão OK')
        : `Falha: ${res.erro}`;
    } catch {
      testeStatus = 'fail';
      testeMensagem = 'Erro ao testar conexão.';
    } finally {
      testando = false;
    }
  }

  async function gerarSsoApiKey() {
    ssoGerando = true;
    try {
      const res = await api.gerarSsoApiKey(empresa.id);
      ssoApiKeyGerada = res.api_key;
    } catch (e) {
      erro = e.message || 'Erro ao gerar chave de API.';
    } finally {
      ssoGerando = false;
    }
  }

  async function testarSsoAcesso() {
    ssoTestando = true;
    ssoTesteStatus = null;
    try {
      const res = await api.testarSsoAcesso({
        empresa_id: empresa.id,
        query: empresa.sso_query_acesso,
        codigo_usuario: ssoTesteCodigoUsuario,
      });
      ssoTesteStatus = res.ok ? 'ok' : 'fail';
      ssoTesteResultado = res.ok
        ? (res.slugs.length ? `Painéis liberados: ${res.slugs.join(', ')}` : 'Nenhum painel liberado pra esse código')
        : `Falha: ${res.erro}`;
    } catch {
      ssoTesteStatus = 'fail';
      ssoTesteResultado = 'Erro ao testar a query.';
    } finally {
      ssoTestando = false;
    }
  }

  async function salvar() {
    validarSlug();
    if (slugErro) return;
    erro = '';
    salvando = true;
    try {
      const payload = {
        slug:    empresa.slug,
        nome:    empresa.nome,
        db_host: empresa.db_host,
        db_port: empresa.db_port,
        db_name: empresa.db_name,
        db_user: empresa.db_user,
        ativo:   empresa.ativo,
        sso_query_acesso: empresa.sso_query_acesso ?? null,
      };
      // Only include db_pass if user typed a new value
      if (empresa.db_pass) {
        payload.db_pass = empresa.db_pass;
      }
      await api.atualizarEmpresa(empresa.id, payload);
      if (logoFile) {
        const fd = new FormData();
        fd.append('file', logoFile);
        await api.uploadLogo(empresa.id, fd);
      }
      goto('/configuracoes/empresas');
    } catch (e) {
      erro = e.message || 'Erro ao salvar.';
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Editar Empresa — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Editar Empresa</h2>
    <a href="/configuracoes/empresas" class="btn-ghost">← Voltar</a>
  </div>

  {#if empresa}
    <div class="form card">
      <section>
        <h3>Dados da Empresa</h3>
        <label>
          Nome da empresa
          <input bind:value={empresa.nome} required />
        </label>
        <label>
          Slug (identificador único)
          <input bind:value={empresa.slug} on:input={validarSlug} required />
          {#if slugErro}<span class="field-error">{slugErro}</span>{/if}
        </label>
        <label>
          Logo
          <input type="file" accept="image/*" on:change={onLogoChange} />
          {#if logoPreview}
            <img class="logo-preview" src={logoPreview} alt="novo logo" />
          {:else if empresa.logo_url}
            <img
              class="logo-preview"
              src={empresa.logo_url}
              alt={empresa.nome}
              on:error={(e) => { e.target.style.display = 'none'; }}
            />
          {/if}
        </label>
      </section>

      <section>
        <h3>Conexão com o Banco</h3>
        <label>
          Host
          <input bind:value={empresa.db_host} required />
        </label>
        <div class="row">
          <label style="flex:1">
            Porta
            <input type="number" bind:value={empresa.db_port} min="1" max="65535" />
          </label>
          <label style="flex:2">
            Banco
            <input bind:value={empresa.db_name} required />
          </label>
        </div>
        <label>
          Usuário
          <input bind:value={empresa.db_user} required />
        </label>
        <label>
          Senha
          <input type="password" bind:value={empresa.db_pass} placeholder="••••••  (deixe em branco para não alterar)" />
        </label>

        <button
          class="btn-ghost btn-test"
          on:click={testarConexao}
          disabled={testando || !empresa.db_host || !empresa.db_name}
        >
          {testando ? 'Testando...' : 'Testar Conexão'}
        </button>

        {#if testeStatus === 'ok'}
          <p class="status-ok">✓ {testeMensagem}</p>
        {:else if testeStatus === 'fail'}
          <p class="status-fail">✗ {testeMensagem}</p>
        {/if}
      </section>

      <section>
        <h3>SSO Externo</h3>

        <button
          class="btn-ghost btn-test"
          on:click={gerarSsoApiKey}
          disabled={ssoGerando}
        >
          {ssoGerando ? 'Gerando...' : 'Gerar/Regenerar Chave de API'}
        </button>

        {#if ssoApiKeyGerada}
          <p class="status-ok">
            Chave gerada — copie agora, não será mostrada de novo:<br />
            <code>{ssoApiKeyGerada}</code>
          </p>
        {/if}

        <label>
          Query de acesso (recebe $1 = codigo_usuario, devolve coluna painel_slug)
          <textarea
            bind:value={empresa.sso_query_acesso}
            rows="4"
            placeholder="SELECT painel_slug FROM minha_tabela WHERE codigo_usuario = $1"
          ></textarea>
        </label>

        <div class="row">
          <label style="flex:1">
            Código de usuário de exemplo
            <input bind:value={ssoTesteCodigoUsuario} placeholder="ex: user_123" />
          </label>
        </div>

        <button
          class="btn-ghost btn-test"
          on:click={testarSsoAcesso}
          disabled={ssoTestando || !empresa.sso_query_acesso || !ssoTesteCodigoUsuario}
        >
          {ssoTestando ? 'Testando...' : 'Testar Query'}
        </button>

        {#if ssoTesteStatus === 'ok'}
          <p class="status-ok">✓ {ssoTesteResultado}</p>
        {:else if ssoTesteStatus === 'fail'}
          <p class="status-fail">✗ {ssoTesteResultado}</p>
        {/if}
      </section>

      {#if erro}<p class="error">{erro}</p>{/if}

      <div class="actions">
        <a href="/configuracoes/empresas" class="btn-ghost">Cancelar</a>
        <button
          class="btn-primary"
          on:click={salvar}
          disabled={salvando || !!slugErro}
        >
          {salvando ? 'Salvando...' : 'Salvar Alterações'}
        </button>
      </div>
    </div>
  {:else}
    <p class="muted">Carregando...</p>
  {/if}
</div>

<style>
.page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { font-size: 20px; color: var(--text); font-family: var(--font-display); }
.error { color: var(--danger, #f85149); font-size: 13px; }
h3 { font-size: 15px; color: var(--text); margin: 0 0 16px; }
.form { max-width: 560px; display: flex; flex-direction: column; gap: 32px; padding: 24px; }
section { display: flex; flex-direction: column; gap: 12px; }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
.row { display: flex; gap: 12px; }
.logo-preview { width: 80px; height: 80px; object-fit: contain; border-radius: 8px; margin-top: 8px; border: 1px solid var(--border); }
.actions { display: flex; gap: 12px; justify-content: flex-end; }
.btn-test { color: var(--accent-blue); border-color: var(--accent-blue); width: fit-content; }
.status-ok  { color: #3fb950; font-size: 13px; padding: 8px 12px; background: #1a4731; border-radius: var(--radius); }
.status-fail { color: #f85149; font-size: 13px; padding: 8px 12px; background: #3d1a1a; border-radius: var(--radius); }
.field-error { color: #f85149; font-size: 12px; }
.muted { color: var(--muted); }
textarea { font-family: monospace; font-size: 13px; padding: 8px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface); color: var(--text); resize: vertical; }
</style>
