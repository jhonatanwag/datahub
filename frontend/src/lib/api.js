const BASE = import.meta.env.VITE_API_URL || '';

async function request(path, options = {}) {
  const tok = localStorage.getItem('token');
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
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Auth
  login: (email, senha, company_slug) =>
    request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, senha, company_slug }) }),
  me: () => request('/api/auth/me'),
  logout: () => request('/api/auth/logout', { method: 'POST' }),

  // Charts (dinâmico por slug)
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
  perguntarIA:  (pergunta) =>
    request('/api/ai/ask', { method: 'POST', body: JSON.stringify({ pergunta }) }),
  historicoIA:  () => request('/api/ai/historico'),

  // Reports
  solicitarRelatorio: (tipo = 'relatorio_mensal') =>
    request('/api/reports/solicitar', { method: 'POST', body: JSON.stringify({ tipo }) }),
  statusRelatorio: (id) => request(`/api/reports/status/${id}`),
  resultadoRelatorio: (id) => request(`/api/reports/resultado/${id}`),

  // Queries (admin)
  listarQueries: (tipo, empresa_id) => {
    const p = new URLSearchParams();
    if (tipo) p.append('tipo', tipo);
    if (empresa_id) p.append('empresa_id', String(empresa_id));
    return request(`/api/queries/?${p}`);
  },
  buscarQuery:    (id)   => request(`/api/queries/${id}`),
  criarQuery:     (data) => request('/api/queries/', { method: 'POST', body: JSON.stringify(data) }),
  atualizarQuery: (id, data) =>
    request(`/api/queries/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deletarQuery:   (id)   => request(`/api/queries/${id}`, { method: 'DELETE' }),
  testarQuery:    (data) =>
    request('/api/queries/testar', { method: 'POST', body: JSON.stringify(data) }),
  executarQuery:  (slug, params = {}) => {
    const p = new URLSearchParams(params);
    return request(`/api/queries/executar/${slug}?${p}`);
  },
  layoutDashboard: () => request('/api/queries/layout/dashboard'),
};
