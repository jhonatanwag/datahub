<script>
  import { onMount, onDestroy } from 'svelte';
  import { goto, beforeNavigate } from '$app/navigation';
  import { page } from '$app/stores';
  import { token, usuario, empresaAtiva, isAdmin, logout } from '$lib/stores/auth.js';
  import { api } from '$lib/api.js';
  import '../app.css';

  const PUBLIC_ROUTES = ['/login', '/selecionar-empresa'];

  let sidebarOpen = true;
  let isMobile    = false;

  // ── Ícones SVG (Lucide stroke, viewBox 0 0 24 24) ──────────────
  const I = {
    home:    `<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9,22 9,12 15,12 15,22"/>`,
    chat:    `<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>`,
    chart:   `<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>`,
    grid:    `<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>`,
    sliders: `<line x1="4" y1="6" x2="20" y2="6"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/><circle cx="10" cy="6" r="2"/><circle cx="14" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>`,
    db:      `<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>`,
    building:`<rect x="3" y="7" width="18" height="13" rx="1"/><path d="M3 7V6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v1"/><line x1="8" y1="21" x2="8" y2="11"/><line x1="16" y1="21" x2="16" y2="11"/><line x1="12" y1="21" x2="12" y2="11"/>`,
    users:   `<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>`,
    logout:  `<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>`,
    menu:    `<line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>`,
    close:   `<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>`,
    chevL:   `<polyline points="15 18 9 12 15 6"/>`,
    chevR:   `<polyline points="9 18 15 12 9 6"/>`,
  };

  function svg(path) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
  }

  const navLinks = [
    { href: '/',   label: 'Dashboard', icon: I.home  },
    { href: '/ai', label: 'IA / Chat', icon: I.chat  },
  ];

  const adminLinks = [
    { href: '/configuracoes/paineis',   label: 'Painéis',   icon: I.grid     },
    { href: '/configuracoes/variaveis', label: 'Variáveis', icon: I.sliders  },
    { href: '/configuracoes/queries',   label: 'Queries',   icon: I.db       },
    { href: '/configuracoes/empresas',  label: 'Empresas',  icon: I.building },
    { href: '/configuracoes/usuarios',  label: 'Usuários',  icon: I.users    },
  ];

  let menuPaineis = [];

  async function carregarMenu() {
    try { menuPaineis = await api.meuMenu(); }
    catch (e) { console.error('Erro ao carregar menu:', e); }
  }

  function updateBreakpoint() {
    const w = window.innerWidth;
    isMobile = w <= 768;
    if (isMobile)       sidebarOpen = false;
    else if (w <= 1024) sidebarOpen = false; // tablet: rail fechado por padrão
    else                sidebarOpen = true;  // desktop: aberto por padrão
  }

  onMount(() => {
    updateBreakpoint();
    window.addEventListener('resize', updateBreakpoint);
  });

  onDestroy(() => {
    if (typeof window !== 'undefined')
      window.removeEventListener('resize', updateBreakpoint);
  });

  onMount(async () => {
    const path = $page.url.pathname;
    if (PUBLIC_ROUTES.includes(path)) return;

    const tok = localStorage.getItem('token');
    if (!tok) { goto('/login'); return; }

    if (!$usuario) {
      try {
        const me = await api.me();
        usuario.set(me);
        carregarMenu();
        if (!$empresaAtiva) {
          empresaAtiva.set({
            id: me.empresa_id, slug: me.company_slug,
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
    if (isMobile) sidebarOpen = false; // fecha ao navegar no mobile
  });

  async function handleLogout() {
    await api.logout().catch(() => {});
    logout();
    goto('/login');
  }

  function trocarEmpresa() { logout(); goto('/login'); }

  function isActive(href) {
    if (href === '/') return $page.url.pathname === '/';
    return $page.url.pathname === href || $page.url.pathname.startsWith(href + '/');
  }

  $: collapsed = !isMobile && !sidebarOpen;
  $: tooltipAtivo = collapsed; // mostra title nos itens só quando colapsado
  $: if (typeof document !== 'undefined' && $usuario?.tema) {
    document.documentElement.setAttribute('data-theme', $usuario.tema);
  }
</script>

{#if PUBLIC_ROUTES.includes($page.url.pathname)}
  <slot />
{:else}
  <div class="shell">

    <!-- Backdrop mobile -->
    {#if isMobile && sidebarOpen}
      <div class="backdrop" on:click={() => sidebarOpen = false} aria-hidden="true"></div>
    {/if}

    <!-- Sidebar -->
    <nav
      class="sidebar"
      class:collapsed
      class:mobile-overlay={isMobile}
      class:mobile-open={isMobile && sidebarOpen}
    >
      <!-- Header -->
      <div class="sidebar-header">
        {#if !collapsed}
          <span class="logo">DataHub</span>
        {/if}
        <button
          class="icon-btn toggle-btn"
          on:click={() => sidebarOpen = !sidebarOpen}
          aria-label={sidebarOpen ? 'Recolher menu' : 'Expandir menu'}
        >
          {@html svg(isMobile
            ? (sidebarOpen ? I.close  : I.menu)
            : (sidebarOpen ? I.chevL : I.chevR))}
        </button>
      </div>

      <!-- Links -->
      <ul class="nav-links">
        {#each navLinks as link}
          <li class:active={isActive(link.href)}>
            <a href={link.href} title={tooltipAtivo ? link.label : null}>
              <span class="nav-icon">{@html svg(link.icon)}</span>
              <span class="nav-label">{link.label}</span>
            </a>
          </li>
        {/each}

        {#if menuPaineis.length > 0}
          <li class="nav-section"><span class="nav-label">Meus Painéis</span></li>
          {#each menuPaineis as painel}
            <li class:active={isActive(`/painel/${painel.slug}`)}>
              <a href="/painel/{painel.slug}" title={tooltipAtivo ? painel.nome : null}>
                <span class="nav-icon">{@html svg(I.chart)}</span>
                <span class="nav-label">{painel.nome}</span>
              </a>
            </li>
          {/each}
        {/if}

        {#if $isAdmin}
          <li class="nav-section"><span class="nav-label">Admin</span></li>
          {#each adminLinks as link}
            <li class:active={isActive(link.href)}>
              <a href={link.href} title={tooltipAtivo ? link.label : null}>
                <span class="nav-icon">{@html svg(link.icon)}</span>
                <span class="nav-label">{link.label}</span>
              </a>
            </li>
          {/each}
        {/if}
      </ul>

      <!-- Logout -->
      <button class="logout-btn" on:click={handleLogout} title={tooltipAtivo ? 'Sair' : null}>
        <span class="nav-icon">{@html svg(I.logout)}</span>
        <span class="nav-label">Sair</span>
      </button>
    </nav>

    <!-- Conteúdo -->
    <div class="main-wrap">
      <header class="topbar">
        <!-- Hamburger só no mobile -->
        {#if isMobile}
          <button class="icon-btn hamburger" on:click={() => sidebarOpen = !sidebarOpen} aria-label="Menu">
            {@html svg(sidebarOpen ? I.close : I.menu)}
          </button>
        {/if}

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

      <main class="content"><slot /></main>
    </div>
  </div>
{/if}

<style>
/* ── Shell ─────────────────────────────────────────────── */
.shell { display: flex; height: 100vh; overflow: hidden; }

/* ── Sidebar ────────────────────────────────────────────── */
.sidebar {
  width: 220px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
  transition: width .2s ease;
}

.sidebar.collapsed { width: 56px; }

/* Header */
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  height: 52px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.sidebar.collapsed .sidebar-header { justify-content: center; }

.logo {
  font-family: var(--font-display);
  font-size: 15px;
  color: var(--accent);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
}

/* Nav links */
.nav-links {
  list-style: none;
  flex: 1;
  padding: 6px 0;
  margin: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.nav-links li a {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  color: var(--muted);
  font-size: 14px;
  text-decoration: none;
  border-radius: 6px;
  margin: 1px 6px;
  transition: background .15s, color .15s;
  white-space: nowrap;
  overflow: hidden;
}
.nav-links li a:hover { color: var(--text); background: var(--surface2); }
.nav-links li.active a {
  color: var(--text);
  background: var(--surface2);
  box-shadow: inset 2px 0 0 var(--accent-blue);
}

/* Icon */
.nav-icon {
  flex-shrink: 0;
  width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
}
.nav-icon :global(svg) { width: 18px; height: 18px; }

/* Label — fade out when collapsed */
.nav-label {
  overflow: hidden;
  opacity: 1;
  max-width: 160px;
  transition: opacity .15s, max-width .2s;
}
.sidebar.collapsed .nav-label { opacity: 0; max-width: 0; pointer-events: none; }

/* Section header */
.nav-section {
  display: flex;
  align-items: center;
  padding: 14px 16px 4px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--muted);
  overflow: hidden;
  height: 34px;
  transition: height .2s, opacity .15s, padding .2s;
}
.sidebar.collapsed .nav-section { height: 8px; opacity: 0; padding: 0; pointer-events: none; }

/* Logout */
.logout-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  margin: 4px 6px 8px;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted);
  font-size: 14px;
  border-radius: 6px;
  white-space: nowrap;
  overflow: hidden;
  transition: background .15s, color .15s;
  width: calc(100% - 12px);
}
.logout-btn:hover { color: var(--danger, #f85149); background: var(--surface2); }

/* Toggle button */
.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted);
  padding: 6px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background .15s, color .15s;
}
.icon-btn:hover { background: var(--surface2); color: var(--text); }
.icon-btn :global(svg) { width: 18px; height: 18px; }

/* ── Mobile overlay ─────────────────────────────────────── */
.backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,.6);
  z-index: 99;
  backdrop-filter: blur(2px);
}

.sidebar.mobile-overlay {
  position: fixed;
  top: 0; left: 0; bottom: 0;
  z-index: 100;
  width: 260px !important;
  transform: translateX(-100%);
  transition: transform .25s ease;
  box-shadow: 4px 0 24px rgba(0,0,0,.5);
}
.sidebar.mobile-overlay.mobile-open { transform: translateX(0); }

.hamburger { display: none; }

@media (max-width: 768px) {
  .hamburger { display: flex; }
  .topbar { gap: 8px; }
  .empresa-nome { display: none; }
}

/* ── Tablet (769–1024) ──────────────────────────────────── */
@media (max-width: 1024px) and (min-width: 769px) {
  /* sidebar começa colapsada (controlado por JS), nada extra aqui */
}

/* ── TV / telas grandes (1920+) ─────────────────────────── */
@media (min-width: 1920px) {
  .sidebar              { width: 260px; }
  .sidebar.collapsed    { width: 72px; }
  .nav-links li a,
  .logout-btn           { font-size: 16px; padding: 12px 14px; gap: 14px; }
  .nav-icon :global(svg){ width: 22px; height: 22px; }
  .logo                 { font-size: 18px; }
  .topbar               { height: 60px; padding: 0 28px; }
  .content              { font-size: 16px; }
}

/* ── Main wrap ──────────────────────────────────────────── */
.main-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 52px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.topbar-empresa { display: flex; align-items: center; gap: 10px; }
.empresa-logo { width: 28px; height: 28px; object-fit: contain; border-radius: 4px; }
.empresa-nome { font-size: 14px; font-weight: 500; color: var(--text); }
.btn-sm { font-size: 12px; padding: 4px 10px; }

.topbar-user { display: flex; align-items: center; gap: 8px; }
.user-avatar {
  width: 30px; height: 30px;
  border-radius: 50%;
  background: var(--accent);
  color: #0d1117;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700;
  flex-shrink: 0;
}
.user-nome { font-size: 13px; color: var(--muted); }

@media (max-width: 480px) {
  .user-nome { display: none; }
  .btn-sm { display: none; }
}

.content { flex: 1; overflow-y: auto; }
</style>
