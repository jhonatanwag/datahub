<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { token, empresa, usuario } from '$lib/stores/company.js';
  import { api } from '$lib/api.js';
  import '../app.css';

  let sidebarOpen = true;

  const navLinks = [
    { href: '/',                      label: 'Dashboard'   },
    { href: '/ai',                    label: 'IA / Chat'   },
    { href: '/configuracoes/queries', label: 'Config'      },
  ];

  onMount(async () => {
    const tok = localStorage.getItem('token');
    if (!tok && $page.url.pathname !== '/login') {
      goto('/login');
      return;
    }
    if (tok && !$usuario) {
      try {
        const me = await api.me();
        usuario.set(me);
        empresa.set({ nome: me.company_name, slug: me.company_slug });
      } catch {
        localStorage.removeItem('token');
        token.set(null);
        goto('/login');
      }
    }
  });
</script>

{#if $page.url.pathname === '/login'}
  <slot />
{:else}
  <div class="shell">
    <nav class="sidebar" class:collapsed={!sidebarOpen}>
      <div class="sidebar-header">
        <span class="logo">DataHub</span>
        <button class="btn-ghost icon-btn" on:click={() => sidebarOpen = !sidebarOpen}>≡</button>
      </div>

      {#if $empresa}
        <div class="empresa-badge">{$empresa.nome}</div>
      {/if}

      <ul class="nav-links">
        {#each navLinks as link}
          <li class:active={$page.url.pathname === link.href}>
            <a href={link.href}>{link.label}</a>
          </li>
        {/each}
      </ul>

      <button class="btn-ghost logout" on:click={async () => {
        await api.logout().catch(() => {});
        localStorage.removeItem('token');
        token.set(null);
        usuario.set(null);
        goto('/login');
      }}>Sair</button>
    </nav>

    <main class="content">
      <slot />
    </main>
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
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 0 16px 16px; }
.logo { font-family: var(--font-display); font-size: 16px; color: var(--accent); font-weight: 500; }
.empresa-badge { margin: 0 12px 12px; padding: 6px 10px; background: var(--surface2); border-radius: var(--radius); font-size: 12px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nav-links { list-style: none; flex: 1; }
.nav-links li a { display: block; padding: 10px 20px; color: var(--muted); font-size: 14px; }
.nav-links li.active a { color: var(--text); background: var(--surface2); border-left: 2px solid var(--accent-blue); }
.nav-links li a:hover { color: var(--text); background: var(--surface2); text-decoration: none; }
.logout { margin: 8px 12px 0; width: calc(100% - 24px); }
.content { flex: 1; overflow-y: auto; }
.icon-btn { padding: 4px 8px; }
</style>
