-- Login web com usuário/senha do app (PsoEducare): chave de integração (X-API-Key) do PsoEducare
-- de cada empresa. A URL usada é a url_impressao_base que a empresa já tem.
-- Rodar no datahub_meta de cada ambiente ANTES do deploy.
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS app_login_api_key TEXT;
