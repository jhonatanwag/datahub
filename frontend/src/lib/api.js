const BASE = import.meta.env.VITE_API_URL || '';

async function request(path, options = {}) {
    const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
    const res = await fetch(`${BASE}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
            ...options.headers,
        },
    });
    if (!res.ok) {
        const text = await res.text();
        let msg;
        try { msg = JSON.parse(text).detail || text; } catch { msg = text; }
        throw new Error(msg || `HTTP ${res.status}`);
    }
    return res.json();
}

export const api = {
    // Auth
    login: (email, senha) =>
        request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, senha }) }),

    selecionarEmpresa: (session_token, empresa_id) =>
        request('/api/auth/selecionar-empresa', {
            method: 'POST',
            body: JSON.stringify({ session_token, empresa_id })
        }),

    minhasEmpresas: () => request('/api/auth/minhas-empresas'),
    me: () => request('/api/auth/me'),
    atualizarTema: (tema) => request('/api/auth/tema', { method: 'PUT', body: JSON.stringify({ tema }) }),

    logout: () => request('/api/auth/logout', { method: 'POST' }),

    ssoTrocar: (exchange) =>
        request('/api/auth/sso/trocar', { method: 'POST', body: JSON.stringify({ exchange }) }),

    // Charts
    chart: (slug, params = {}) => {
        const p = new URLSearchParams(params);
        return request(`/api/charts/${slug}?${p}`);
    },

    // Tables
    pedidos: (params = {}) => {
        const p = new URLSearchParams(params);
        return request(`/api/tables/pedidos?${p}`);
    },

    // IA
    perguntarIA: (pergunta) =>
        request('/api/ai/ask', { method: 'POST', body: JSON.stringify({ pergunta }) }),
    historicoIA: () => request('/api/ai/historico'),

    // Reports
    solicitarRelatorio: (tipo = 'relatorio_mensal') =>
        request('/api/reports/solicitar', { method: 'POST', body: JSON.stringify({ tipo }) }),
    statusRelatorio: (id) => request(`/api/reports/status/${id}`),
    resultadoRelatorio: (id) => request(`/api/reports/resultado/${id}`),

    // Queries (admin)
    parametrosQuery:       (id)     => request(`/api/queries/${id}/parametros`),
    salvarParametrosQuery: (id, d)  => request(`/api/queries/${id}/parametros`, { method: 'PUT', body: JSON.stringify(d) }),

    listarQueries: (tipo, empresa_id) => {
        const p = new URLSearchParams();
        if (tipo) p.append('tipo', tipo);
        if (empresa_id) p.append('empresa_id', String(empresa_id));
        return request(`/api/queries/?${p}`);
    },
    buscarQuery:    (id)       => request(`/api/queries/${id}`),
    criarQuery:     (data)     => request('/api/queries/', { method: 'POST', body: JSON.stringify(data) }),
    atualizarQuery: (id, data) => request(`/api/queries/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    deletarQuery:   (id)       => request(`/api/queries/${id}`, { method: 'DELETE' }),
    testarQuery:    (data)     => request('/api/queries/testar', { method: 'POST', body: JSON.stringify(data) }),
    executarQuery:  (slug, params = {}) => {
        const p = new URLSearchParams(params);
        return request(`/api/queries/executar/${slug}?${p}`);
    },
    layoutDashboard: () => request('/api/queries/layout/dashboard'),

    // Empresas (admin)
    listarEmpresas:   ()         => request('/api/empresas/'),
    buscarEmpresa:    (id)       => request(`/api/empresas/${id}`),
    criarEmpresa:     (data)     => request('/api/empresas/', { method: 'POST', body: JSON.stringify(data) }),
    atualizarEmpresa: (id, data) => request(`/api/empresas/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    desativarEmpresa: (id)       => request(`/api/empresas/${id}`, { method: 'DELETE' }),
    reativarEmpresa:  (id)       => request(`/api/empresas/${id}/reativar`, { method: 'POST' }),
    testarConexao:    (data)     => request('/api/empresas/testar-conexao', { method: 'POST', body: JSON.stringify(data) }),
    gerarSsoApiKey: (id) => request(`/api/empresas/${id}/sso-api-key`, { method: 'POST' }),
    testarSsoAcesso: (data) => request('/api/empresas/testar-sso-acesso', { method: 'POST', body: JSON.stringify(data) }),

    uploadLogo: (id, formData) => {
        const tok = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
        return fetch(`${BASE}/api/empresas/${id}/logo`, {
            method: 'POST',
            headers: tok ? { Authorization: `Bearer ${tok}` } : {},
            body: formData,
        }).then(r => r.json());
    },

    // Usuários (admin)
    listarUsuarios:    ()                => request('/api/usuarios/'),
    criarUsuario:      (data)            => request('/api/usuarios/', { method: 'POST', body: JSON.stringify(data) }),
    atualizarUsuario:  (id, data)        => request(`/api/usuarios/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    desativarUsuario:  (id)              => request(`/api/usuarios/${id}`, { method: 'DELETE' }),
    vincularEmpresas:  (id, empresa_ids) =>
        request(`/api/usuarios/${id}/empresas`, { method: 'POST', body: JSON.stringify({ empresa_ids }) }),
    listarEmpresasUsuario: (id)          => request(`/api/usuarios/${id}/empresas`),

    // Variáveis
    listarVariaveis:        ()          => request('/api/variaveis/'),
    buscarVariavel:         (id)        => request(`/api/variaveis/${id}`),
    criarVariavel:          (d)         => request('/api/variaveis/', { method: 'POST', body: JSON.stringify(d) }),
    atualizarVariavel:      (id, d)     => request(`/api/variaveis/${id}`, { method: 'PATCH', body: JSON.stringify(d) }),
    desativarVariavel:      (id)        => request(`/api/variaveis/${id}`, { method: 'DELETE' }),
    executarFonteVariavel:  (id, empresa_id) => request(`/api/variaveis/executar-fonte/${id}${empresa_id ? `?empresa_id=${empresa_id}` : ''}`),
    testarFonteVariavel:    (query_fonte, empresa_id) => request('/api/variaveis/testar-fonte', { method: 'POST', body: JSON.stringify({ query_fonte, empresa_id }) }),

    // Painéis
    listarPaineis:          ()          => request('/api/paineis/'),
    meuMenu:                ()          => request('/api/paineis/meu-menu'),
    meuDashboard:           ()          => request('/api/paineis/meu-dashboard'),
    buscarPainel:           (id)        => request(`/api/paineis/${id}`),
    buscarPainelPorSlug:    (slug)      => request(`/api/paineis/slug/${slug}`),
    criarPainel:            (d)         => request('/api/paineis/', { method: 'POST', body: JSON.stringify(d) }),
    atualizarPainel:        (id, d)     => request(`/api/paineis/${id}`, { method: 'PATCH', body: JSON.stringify(d) }),
    desativarPainel:        (id)        => request(`/api/paineis/${id}`, { method: 'DELETE' }),

    // Indicadores do painel
    indicadoresPainel:      (id)        => request(`/api/paineis/${id}/indicadores`),
    salvarIndicadores:      (id, d)     => request(`/api/paineis/${id}/indicadores`, { method: 'PUT', body: JSON.stringify(d) }),

    // Variáveis do painel
    variaveisPainel:        (id)        => request(`/api/paineis/${id}/variaveis`),
    salvarVariaveisPainel:  (id, d)     => request(`/api/paineis/${id}/variaveis`, { method: 'PUT', body: JSON.stringify(d) }),

    // Usuários do painel
    usuariosPainel:         (id)        => request(`/api/paineis/${id}/usuarios`),
    salvarUsuariosPainel:   (id, d)     => request(`/api/paineis/${id}/usuarios`, { method: 'PUT', body: JSON.stringify(d) }),

    // Renderização
    renderizarPainel: (id, filtros) => {
        const p = new URLSearchParams(filtros || {});
        return request(`/api/paineis/${id}/renderizar?${p}`);
    },
};
