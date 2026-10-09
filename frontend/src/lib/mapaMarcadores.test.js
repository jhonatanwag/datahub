import { test } from 'node:test';
import assert from 'node:assert/strict';
import { escaparHtml, idsTiposComImagem, htmlPopup, htmlMarcadorFoto } from './mapaMarcadores.js';

test('escaparHtml neutraliza tags e aspas; null/undefined viram vazio', () => {
  assert.equal(escaparHtml('<b>x</b> & "y"'), '&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;');
  assert.equal(escaparHtml(null), '');
  assert.equal(escaparHtml(undefined), '');
  assert.equal(escaparHtml(0), '0');
});

test('idsTiposComImagem: ids únicos, numéricos e ordenados; ignora vazios/inválidos', () => {
  const pontos = [
    { tip_veic_id: 3 }, { tip_veic_id: '17' }, { tip_veic_id: 3 },
    { tip_veic_id: null }, { tip_veic_id: '' }, { tip_veic_id: 'abc' }, {}, { tip_veic_id: 0 },
  ];
  assert.deepEqual(idsTiposComImagem(pontos), [3, 17]);
  assert.deepEqual(idsTiposComImagem([]), []);
  assert.deepEqual(idsTiposComImagem(undefined), []);
});

test('htmlPopup: label em negrito, valor e detalhe opcional, tudo escapado', () => {
  assert.equal(htmlPopup({ label: 'TR-10', valor: 5 }), '<b>TR-10</b><br>5');
  assert.equal(
    htmlPopup({ label: '<i>x</i>', valor: 2, detalhe: 'Pendência em 01/10/2026 & mais' }),
    '<b>&lt;i&gt;x&lt;/i&gt;</b><br>2<br><span class="mp-detalhe">Pendência em 01/10/2026 &amp; mais</span>',
  );
  assert.equal(htmlPopup({ label: 'A', valor: null }), '<b>A</b>');
});

test('htmlMarcadorFoto: círculo com a imagem e a cor da borda', () => {
  const h = htmlMarcadorFoto('blob:http://x/abc', '#3FCF9F', 44);
  assert.match(h, /class="mp-foto"/);
  assert.match(h, /width:44px;height:44px/);
  assert.match(h, /border-color:#3FCF9F/);
  assert.match(h, /<img src="blob:http:\/\/x\/abc" alt="">/);
});
