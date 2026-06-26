<script>
  import { goto } from '$app/navigation';
  import { api } from '$lib/api.js';

  let nome    = '';
  let slug    = '';
  let db_host = '';
  let db_port = 5432;
  let db_name = '';
  let db_user = '';
  let db_pass = '';
  let logoFile    = null;
  let logoPreview = null;

  let testeStatus   = null; // null | 'ok' | 'fail'
  let testeMensagem = '';
  let testando      = false;
  let salvando      = false;
  let erro          = '';
  let slugErro      = '';

  function gerarSlug(valor) {
    return valor.toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '');
  }

  function onNomeInput() {
    slug = gerarSlug(nome);
    validarSlug();
  }

  function validarSlug() {
    if (!slug) {
      slugErro = '';
      return;
    }
    if (/\s/.test(slug)) {
      slugErro = 'Slug não pode conter espaços.';
    } else if (!/^[a-z0-9-]+$/.test(slug)) {
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
        host: db_host,
        port: db_port,
        database: db_name,
        user: db_user,
        password: db_pass
      });
      if (res.ok) {
        testeStatus = 'ok';
        testeMensagem = res.tabelas != null
          ? `Conexão OK — ${res.tabelas} tabelas encontradas`
          : 'Conexão OK';
      } else {
        testeStatus = 'fail';
        testeMensagem = `Falha: ${res.erro}`;
      }
    } catch (e) {
      testeStatus = 'fail';
      testeMensagem = 'Erro ao testar conexão.';
    } finally {
      testando = false;
    }
  }

  async function salvar() {
    validarSlug();
    if (slugErro) return;
    erro = '';
    salvando = true;
    try {
      const empresa = await api.criarEmpresa({ slug, nome, db_host, db_port, db_name, db_user, db_pass });
      if (logoFile) {
        const fd = new FormData();
        fd.append('file', logoFile);
        await api.uploadLogo(empresa.id, fd);
      }
      goto('/configuracoes/empresas');
    } catch (e) {
      erro = e.message || 'Erro ao salvar empresa.';
    } finally {
      salvando = false;
    }
  }
</script>

<svelte:head><title>Nova Empresa — DataHub</title></svelte:head>

<div class="page">
  <div class="page-header">
    <h2>Nova Empresa</h2>
    <a href="/configuracoes/empresas" class="btn-ghost">← Voltar</a>
  </div>

  <div class="form card">
    <section>
      <h3>Dados da Empresa</h3>
      <label>
        Nome da empresa
        <input bind:value={nome} on:input={onNomeInput} placeholder="Empresa Exemplo Ltda" required />
      </label>
      <label>
        Slug (identificador único)
        <input bind:value={slug} on:input={validarSlug} placeholder="empresa-exemplo" required />
        {#if slugErro}<span class="field-error">{slugErro}</span>{/if}
      </label>
      <label>
        Logo (opcional)
        <input type="file" accept="image/*" on:change={onLogoChange} />
        {#if logoPreview}
          <img class="logo-preview" src={logoPreview} alt="preview do logo" />
        {/if}
      </label>
    </section>

    <section>
      <h3>Conexão com o Banco</h3>
      <label>
        Host
        <input bind:value={db_host} placeholder="db.example.com" required />
      </label>
      <div class="row">
        <label style="flex:1">
          Porta
          <input type="number" bind:value={db_port} min="1" max="65535" />
        </label>
        <label style="flex:2">
          Banco
          <input bind:value={db_name} placeholder="nome_do_banco" required />
        </label>
      </div>
      <label>
        Usuário
        <input bind:value={db_user} placeholder="postgres" required />
      </label>
      <label>
        Senha
        <input type="password" bind:value={db_pass} required />
      </label>

      <button
        class="btn-ghost btn-test"
        on:click={testarConexao}
        disabled={testando || !db_host || !db_name || !db_user}
      >
        {testando ? 'Testando...' : 'Testar Conexão'}
      </button>

      {#if testeStatus === 'ok'}
        <p class="status-ok">✓ {testeMensagem}</p>
      {:else if testeStatus === 'fail'}
        <p class="status-fail">✗ {testeMensagem}</p>
      {/if}
    </section>

    {#if erro}<p class="error">{erro}</p>{/if}

    <div class="actions">
      <a href="/configuracoes/empresas" class="btn-ghost">Cancelar</a>
      <button
        class="btn-primary"
        on:click={salvar}
        disabled={salvando || testeStatus !== 'ok' || !!slugErro}
      >
        {salvando ? 'Salvando...' : 'Salvar Empresa'}
      </button>
    </div>
  </div>
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
</style>
