import { token, usuario, empresaAtiva, menuPaineis } from '$lib/stores/auth.js';
import { api, assetUrl } from '$lib/api.js';

// Guarda o token do acesso externo (SSO ou login com usuário do app) e carrega
// usuário, empresa e menu de painéis liberados.
export async function iniciarSessaoExterna(tokenJwt) {
    token.set(tokenJwt);

    const me = await api.me();
    usuario.set(me);
    empresaAtiva.set({
        id: me.empresa_id, slug: me.company_slug,
        nome: me.company_name,
        logo_url: assetUrl(`/api/empresas/${me.empresa_id}/logo`),
        url_impressao_base: me.url_impressao_base ?? null
    });
    menuPaineis.set(await api.meuMenu());
}
