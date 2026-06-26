<script>
  import { onMount } from 'svelte';
  import { goto, beforeNavigate } from '$app/navigation';
  import { page } from '$app/stores';
  import { token, usuario, empresaAtiva, isAdmin, logout } from '$lib/stores/auth.js';
  import { api } from '$lib/api.js';
  import '../app.css';

  const PUBLIC_ROUTES = ['/login', '/selecionar-empresa'];

  let sidebarOpen = true;

  const navLinks = [
    { href: '/',   label: 'Dashboard' },
    { href: '/ai', label: 'IA / Chat' },
  ];

  const adminLinks = [
    { href: '/configuracoes/empresas', label: 'Empresas'  },
    { href: '/configuracoes/usuarios', label: 'Usuários'  },
    { href: '/configuracoes/queries',  label: 'Queries'   },
  ];

  onMount(async () => {
    const path = $page.url.pathname;
    if (PUBLIC_ROUTES.includes(path)) return;

    const tok = localStorage.getItem('token');
    if (!tok) { goto('/login'); return; }

    if (!$usuario) {
      try {
        const me = await api.me();
        usuario.set(me);
        if (!$empresaAtiva) {
          empresaAtiva.set({
            id: me.empresa_id,
            slug: me.company_slug,
            nome: me.company_name,
            logo_url: `/api/empresas/${me.empresa_id}/logo`
          });
        }
      } catch {
        localStorage.removeItem('token');
        token.set(null);
        goto('/login');
      }
    }
  });

  beforeNavigate(({ to }) => {
    const path = to?.url?.pathname ?? '';
    if (PUBLIC_ROUTES.includes(path)) return;
    const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
    if (!tok) goto('/login');
  });

  async function handleLogout() {
    await api.logout().catch(() => {});
    logout();
    goto('/login');
  }

  function trocarEmpresa() {
    goto('/selecionar-empresa');
  }

  function isActive(href) {
    return $page.url.pathname === href || $page.url.pathname.startsWith(href + '/');
  }
</script>

{#if PUBLIC_ROUTES.includes($page.url.pathname)}
  <slot />
{:else}
  <div class="shell">
    <nav class="sidebar" class:collapsed={!sidebarOpen}>
      <div class="sidebar-header">
        <span class="logo">DataHub</span>
        <button class="btn-ghost icon-btn" on:click={() => sidebarOpen = !sidebarOpen}>≡</button>
      </div>

      <ul class="nav-links">
        {#each navLinks as link}
          <li class:active={isActive(link.href)}>
            <a href={link.href}>{link.label}</a>
          </li>
        {/each}

        {#if $isAdmin}
          <li class="nav-section">Admin</li>
          {#each adminLinks as link}
            <li class:active={isActive(link.href)}>
              <a href={link.href}>{link.label}</a>
            </li>
          {/each}
        {/if}
      </ul>

      <button class="btn-ghost logout" on:click={handleLogout}>Sair</button>
    </nav>

    <div class="main-wrap">
      <header class="topbar">
        <div class="topbar-empresa">
          <img
            src={$empresaAtiva?.logo_url}
            alt={$empresaAtiva?.nome}
            class="empresa-logo"
            on:error={(e) => { e.target.style.display = 'none'; }}
          />
          <span class="empresa-nome">{$empresaAtiva?.nome ?? ''}</span>
          <button class="btn-ghost btn-sm" on:click={trocarEmpresa}>Trocar empresa</button>
        </div>
        <div class="topbar-user">
          <span class="user-avatar">{$usuario?.nome?.charAt(0)?.toUpperCase() ?? '?'}</span>
          <span class="user-nome">{$usuario?.nome ?? ''}</span>
        </div>
      </header>

      <main class="content">
        <slot />
      </main>
    </div>
  </div>
{/if}

<style>
.shell { display: flex; height: 100vh; overflow: hidden; }

.sidebar {
  width: 220px; min-width: 220px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  padding: 16px 0;
  transition: width .2s, min-width .2s;
}
.sidebar.collapsed { width: 56px; min-width: 56px; }

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px 16px;
}
.logo { font-family: var(--font-display); font-size: 16px; color: var(--accent); font-weight: 500; }

.nav-links { list-style: none; flex: 1; padding: 0; margin: 0; }
.nav-links li a {
  display: block; padding: 10px 20px;
  color: var(--muted); font-size: 14px;
}
.nav-links li.active a {
  color: var(--text);
  background: var(--surface2);
  border-left: 2px solid var(--accent-blue);
}
.nav-links li a:hover { color: var(--text); background: var(--surface2); text-decoration: none; }

.nav-section {
  padding: 16px 20px 4px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--muted);
}

.logout { margin: 8px 12px 0; width: calc(100% - 24px); }
.icon-btn { padding: 4px 8px; }

.main-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 52px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.topbar-empresa {
  display: flex;
  align-items: center;
  gap: 10px;
}
.empresa-logo {
  width: 28px; height: 28px;
  object-fit: contain;
  border-radius: 4px;
}
.empresa-nome { font-size: 14px; font-weight: 500; color: var(--text); }
.btn-sm { font-size: 12px; padding: 4px 10px; }

.topbar-user {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-avatar {
  width: 30px; height: 30px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
}
.user-nome { font-size: 13px; color: var(--muted); }

.content { flex: 1; overflow-y: auto; }
</style>
