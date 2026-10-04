-- Painel "Consulta de Usuário" (cad_consulta_usuario) — rodar no datahub_meta.
-- Idempotente: reexecutar apaga e recria o painel/queries/variável deste script.
-- Requer o tipo de query `card` (deploy do backend/frontend com CardPerfil).
BEGIN;

DELETE FROM painel_indicadores WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'cad_consulta_usuario');
DELETE FROM painel_variaveis   WHERE painel_id IN (SELECT id FROM paineis WHERE slug = 'cad_consulta_usuario');
DELETE FROM paineis   WHERE slug = 'cad_consulta_usuario';
DELETE FROM queries   WHERE slug IN ('cad_dados_usuario', 'cad_frentes_usuario') AND empresa_id IS NULL;
DELETE FROM variaveis WHERE slug = 'var_colaborador_usuario';

INSERT INTO variaveis (slug, nome, descricao, tipo, query_fonte, ativo) VALUES (
  'var_colaborador_usuario', 'Colaborador',
  'Colaborador com usuário no sistema (busca por nome)', 'select',
  $q$select f.funcionario_id as valor,
       f.nome_funcionario || ' — Código: ' || f.funcionario_id as label
from funcionario f
inner join usuario u on u.usuario_id = f.funcionario_id
order by f.nome_funcionario$q$, true);

INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id) VALUES (
  'cad_dados_usuario', 'Dados do Usuário', 'Nome, código, login e status do colaborador selecionado',
  $q$select f.nome_funcionario as titulo,
       'Código: ' || f.funcionario_id as subtitulo,
       u.login as "Login",
       u.situacao_cadastro as "Status"
from funcionario f
inner join usuario u on u.usuario_id = f.funcionario_id
where f.funcionario_id = nullif($1::text, '')::bigint$q$,
  'card', 120, true, (SELECT id FROM query_grupos WHERE nome = 'Colaboradores'));

INSERT INTO queries (slug, nome, descricao, sql_texto, tipo, cache_ttl, ativo, grupo_id) VALUES (
  'cad_frentes_usuario', 'Frentes cadastradas', 'Frentes de trabalho vinculadas ao colaborador selecionado',
  $q$select ft.descricao as "Frente",
       coalesce(ft.codigo_frente_trabalho, ft.frente_trabalho_id) as "Código",
       case ft.situacao_cadastro when 'ATIVO' then 'Ativa' else 'Inativa' end as "Status"
from frente_trabalho_func ftf
inner join frente_trabalho ft on ft.frente_trabalho_id = ftf.frente_trabalho_id
where ftf.funcionario_id = nullif($1::text, '')::bigint
order by 1$q$,
  'table', 120, true, (SELECT id FROM query_grupos WHERE nome = 'Colaboradores'));

INSERT INTO query_parametros (query_id, nome, tipo, obrigatorio, variavel_id)
SELECT q.id, 'var_colaborador_usuario', 'text', false, (SELECT id FROM variaveis WHERE slug = 'var_colaborador_usuario')
FROM queries q WHERE q.slug IN ('cad_dados_usuario', 'cad_frentes_usuario') AND q.empresa_id IS NULL;

INSERT INTO paineis (slug, nome, descricao, icone, colunas, ativo, ordem_menu) VALUES (
  'cad_consulta_usuario', 'Consulta de Usuário',
  'Consulte o acesso e as frentes vinculadas ao colaborador.', 'users', 2, true, 3);

INSERT INTO painel_indicadores (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, imprimir)
SELECT p.id, 'cad_dados_usuario', 'Dados do Usuário', 1, 1, 1, 1, 1, true FROM paineis p WHERE p.slug = 'cad_consulta_usuario';
INSERT INTO painel_indicadores (painel_id, query_slug, titulo, linha, coluna, col_span, row_span, posicao, imprimir)
SELECT p.id, 'cad_frentes_usuario', 'Frentes cadastradas', 1, 2, 1, 1, 2, true FROM paineis p WHERE p.slug = 'cad_consulta_usuario';

INSERT INTO painel_variaveis (painel_id, variavel_id, obrigatorio, posicao)
SELECT p.id, v.id, false, 0 FROM paineis p, variaveis v WHERE p.slug = 'cad_consulta_usuario' AND v.slug = 'var_colaborador_usuario';

-- Acesso: libera para os administradores; vincule os demais usuários pela tela do painel.
INSERT INTO painel_usuarios (painel_id, usuario_id)
SELECT p.id, u.id FROM paineis p, usuarios u WHERE p.slug = 'cad_consulta_usuario' AND u.role = 'admin' AND u.ativo = true;

COMMIT;
