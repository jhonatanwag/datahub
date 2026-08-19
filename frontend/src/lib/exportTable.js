import * as XLSX from 'xlsx';
import ExcelJS from 'exceljs';
import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import { get } from 'svelte/store';
import { empresaAtiva } from '$lib/stores/auth.js';

function escaparCSV(valor) {
  // Quebras de linha dentro de um campo (dado real vindo da fonte, ex:
  // texto com \r\n embutido) quebram leitores de CSV que não respeitam
  // aspas — normaliza pra espaço, garantindo que cada linha do arquivo
  // corresponda a exatamente uma linha da tabela.
  const texto = valor === null || valor === undefined
    ? ''
    : String(valor).replace(/[\r\n]+/g, ' ').trim();
  if (/[;"]/.test(texto)) {
    return `"${texto.replace(/"/g, '""')}"`;
  }
  return texto;
}

export function baixarCSV(colunas, dados, titulo) {
  const cabecalho = colunas.map(c => escaparCSV(c.label ?? c.key)).join(';');
  const linhas = dados.map(row =>
    colunas.map(c => escaparCSV(row[c.key])).join(';')
  );
  const conteudo = '﻿' + [cabecalho, ...linhas].join('\r\n');
  const blob = new Blob([conteudo], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const nomeArquivo = `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.csv`;

  const a = document.createElement('a');
  a.href = url;
  a.download = nomeArquivo;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function baixarXLSX(colunas, dados, titulo) {
  const cabecalho = colunas.map(c => c.label ?? c.key);
  const linhas = dados.map(row =>
    colunas.map(c => row[c.key] ?? '')
  );
  const ws = XLSX.utils.aoa_to_sheet([cabecalho, ...linhas]);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Dados');
  const nomeArquivo = `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.xlsx`;
  XLSX.writeFile(wb, nomeArquivo);
}

// Achata a árvore de agrupamento (mesma estrutura que GrupoLinha.svelte percorre
// pra renderizar na tela) numa lista ordenada de linhas de grupo/detalhe, pra
// virar linhas de uma tabela única em qualquer formato de exportação.
function achatarArvore(no, nivel, linhasSaida) {
  if (no.folha) {
    for (const linha of no.linhas) {
      linhasSaida.push({ tipo: 'detalhe', nivel, linha });
    }
    return;
  }
  for (const grupo of no.grupos) {
    linhasSaida.push({ tipo: 'grupo', nivel, valor: grupo.valor, agregados: grupo.agregados });
    achatarArvore(grupo.filho, nivel + 1, linhasSaida);
  }
}

const indentar = nivel => '    '.repeat(nivel);

// Monta as linhas de uma query table_dynamic a partir da árvore de agrupamento,
// junto com o tipo de cada linha ('grupo' | 'detalhe') — reaproveitado pelos
// três formatos de exportação (CSV, Excel, PDF) pra manter grupos e agregações
// consistentes com o que a tela mostra via GrupoLinha.svelte. Formatos que não
// precisam do tipo (CSV) só usam `celulas`.
function linhasAgrupadasComTipo(colunasDetalhe, agregacoes, arvore) {
  const linhasAchatadas = [];
  achatarArvore(arvore, 0, linhasAchatadas);

  return linhasAchatadas.map(item => {
    if (item.tipo === 'grupo') {
      const celulaGrupo = `${indentar(item.nivel)}${item.valor ?? '—'}`;
      const vaziasDetalhe = Array(Math.max(0, colunasDetalhe.length - 1)).fill('');
      const celulasAgregados = agregacoes.map((_, i) => {
        const ag = item.agregados[i];
        return ag ? `${ag.label ?? ag.coluna}: ${ag.valor}` : '';
      });
      return { tipo: 'grupo', celulas: [celulaGrupo, ...vaziasDetalhe, ...celulasAgregados] };
    }

    const celulasDetalhe = colunasDetalhe.map((c, i) => {
      const valor = item.linha[c.key] ?? '';
      return i === 0 ? `${indentar(item.nivel)}${valor}` : valor;
    });
    return { tipo: 'detalhe', celulas: [...celulasDetalhe, ...agregacoes.map(() => '')] };
  });
}

export function baixarCSVAgrupado(colunasDetalhe, agregacoes, arvore, titulo) {
  const cabecalho = [
    ...colunasDetalhe.map(c => escaparCSV(c.label ?? c.key)),
    ...agregacoes.map(a => escaparCSV(a.label ?? a.coluna)),
  ].join(';');
  const linhas = linhasAgrupadasComTipo(colunasDetalhe, agregacoes, arvore)
    .map(({ celulas }) => celulas.map(escaparCSV).join(';'));

  const conteudo = '﻿' + [cabecalho, ...linhas].join('\r\n');
  const blob = new Blob([conteudo], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const nomeArquivo = `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.csv`;

  const a = document.createElement('a');
  a.href = url;
  a.download = nomeArquivo;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const XLSX_FUNDO_CABECALHO = 'FF161B22';
const XLSX_FUNDO_GRUPO     = 'FFDCE3EA';
const XLSX_FUNDO_ZEBRA     = 'FFF3F5F7';

export async function baixarXLSXAgrupado(colunasDetalhe, agregacoes, arvore, titulo) {
  const cabecalho = [
    ...colunasDetalhe.map(c => c.label ?? c.key),
    ...agregacoes.map(a => a.label ?? a.coluna),
  ];
  const linhas = linhasAgrupadasComTipo(colunasDetalhe, agregacoes, arvore);

  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet('Dados');

  const linhaCabecalho = ws.addRow(cabecalho);
  linhaCabecalho.eachCell(celula => {
    celula.font = { bold: true, color: { argb: 'FFFFFFFF' } };
    celula.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: XLSX_FUNDO_CABECALHO } };
  });

  let indiceDetalhe = 0;
  for (const { tipo, celulas } of linhas) {
    const linha = ws.addRow(celulas);
    if (tipo === 'grupo') {
      linha.eachCell(celula => {
        celula.font = { bold: true };
        celula.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: XLSX_FUNDO_GRUPO } };
      });
    } else {
      if (indiceDetalhe % 2 === 1) {
        linha.eachCell(celula => {
          celula.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: XLSX_FUNDO_ZEBRA } };
        });
      }
      indiceDetalhe++;
    }
  }

  ws.columns.forEach(coluna => { coluna.width = 22; });

  const buffer = await wb.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const url = URL.createObjectURL(blob);
  const nomeArquivo = `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.xlsx`;

  const a = document.createElement('a');
  a.href = url;
  a.download = nomeArquivo;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function logoParaDataURL(url) {
  try {
    const resp = await fetch(url);
    if (!resp.ok) return null;
    const blob = await resp.blob();
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload  = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

async function prepararDocumentoPDF(titulo, orientacao = 'retrato') {
  const empresa = get(empresaAtiva);
  const logoUrl = empresa?.logo_url;
  const logoDataUrl = logoUrl ? await logoParaDataURL(logoUrl) : null;
  const nomeEmpresa = empresa?.nome ?? '';
  const emitidoEm = new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short', timeStyle: 'short'
  }).format(new Date());

  const doc = new jsPDF({
    orientation: orientacao === 'paisagem' ? 'landscape' : 'portrait',
    unit: 'mm',
    format: 'a4',
  });
  const margem = 14;
  const larguraPagina = doc.internal.pageSize.getWidth();
  const alturaPagina  = doc.internal.pageSize.getHeight();
  const inicioTexto = logoDataUrl ? margem + 18 : margem;

  return { doc, margem, larguraPagina, alturaPagina, inicioTexto, logoDataUrl, nomeEmpresa, emitidoEm };
}

function desenharCabecalhoPagina(ctx, titulo) {
  const { doc, margem, larguraPagina, inicioTexto, logoDataUrl, nomeEmpresa, emitidoEm } = ctx;
  return () => {
    if (logoDataUrl) {
      doc.addImage(logoDataUrl, margem, 8, 14, 14);
    }
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.text(titulo, inicioTexto, 14);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.text(nomeEmpresa, inicioTexto, 20);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(61, 190, 103);
    doc.text('GPA Analytics', larguraPagina - margem, 14, { align: 'right' });
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(0, 0, 0);
    doc.text(`Emitido em: ${emitidoEm}`, larguraPagina - margem, 20, { align: 'right' });
  };
}

function numerarPaginasPDF({ doc, margem, larguraPagina, alturaPagina }) {
  const totalPaginas = doc.internal.getNumberOfPages();
  for (let i = 1; i <= totalPaginas; i++) {
    doc.setPage(i);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.text(
      `Página ${i} de ${totalPaginas}`,
      larguraPagina - margem,
      alturaPagina - 8,
      { align: 'right' }
    );
  }
}

function salvarPDF(doc, titulo) {
  const nomeArquivo = `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.pdf`;
  doc.save(nomeArquivo);
}

export async function baixarPDF(colunas, dados, titulo, orientacao = 'retrato') {
  const ctx = await prepararDocumentoPDF(titulo, orientacao);
  const cabecalho = colunas.map(c => c.label ?? c.key);
  const linhas = dados.map(row => colunas.map(c => row[c.key] ?? ''));

  autoTable(ctx.doc, {
    head: [cabecalho],
    body: linhas,
    startY: 28,
    margin: { top: 28, left: ctx.margem, right: ctx.margem, bottom: 16 },
    styles: { fontSize: 8, cellPadding: 2 },
    headStyles: { fillColor: [22, 27, 34] },
    didDrawPage: desenharCabecalhoPagina(ctx, titulo),
  });

  numerarPaginasPDF(ctx);
  salvarPDF(ctx.doc, titulo);
}

// PDF de query table_dynamic: reproduz as linhas de grupo (com os valores de
// agregação de cada nível) e a indentação por nível, igual à árvore renderizada
// na tela por GrupoLinha.svelte — diferente de baixarPDF, que só serve tabela plana.
export async function baixarPDFAgrupado(colunasDetalhe, agregacoes, arvore, titulo, orientacao = 'retrato') {
  const ctx = await prepararDocumentoPDF(titulo, orientacao);
  const cabecalho = [
    ...colunasDetalhe.map(c => c.label ?? c.key),
    ...agregacoes.map(a => a.label ?? a.coluna),
  ];

  const linhasAchatadas = [];
  achatarArvore(arvore, 0, linhasAchatadas);

  const body = linhasAchatadas.map(item => {
    if (item.tipo === 'grupo') {
      const estiloGrupo = { fontStyle: 'bold', fillColor: [240, 240, 240] };
      const celulaGrupo = {
        content: `${indentar(item.nivel)}${item.valor ?? '—'}`,
        colSpan: Math.max(1, colunasDetalhe.length),
        styles: estiloGrupo,
      };
      const celulasAgregados = agregacoes.map((_, i) => {
        const ag = item.agregados[i];
        return {
          content: ag ? `${ag.label ?? ag.coluna}: ${ag.valor}` : '',
          styles: { ...estiloGrupo, halign: 'right' },
        };
      });
      return [celulaGrupo, ...celulasAgregados];
    }

    const celulasDetalhe = colunasDetalhe.map((c, i) => {
      const valor = item.linha[c.key] ?? '';
      return i === 0 ? `${indentar(item.nivel)}${valor}` : valor;
    });
    return [...celulasDetalhe, ...agregacoes.map(() => '')];
  });

  autoTable(ctx.doc, {
    head: [cabecalho],
    body,
    startY: 28,
    margin: { top: 28, left: ctx.margem, right: ctx.margem, bottom: 16 },
    styles: { fontSize: 8, cellPadding: 2 },
    headStyles: { fillColor: [22, 27, 34] },
    didDrawPage: desenharCabecalhoPagina(ctx, titulo),
  });

  numerarPaginasPDF(ctx);
  salvarPDF(ctx.doc, titulo);
}
