import * as XLSX from 'xlsx';
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

export async function baixarPDF(colunas, dados, titulo) {
  const empresa = get(empresaAtiva);
  const logoUrl = empresa?.logo_url;
  const logoDataUrl = logoUrl ? await logoParaDataURL(logoUrl) : null;
  const nomeEmpresa = empresa?.nome ?? '';
  const emitidoEm = new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short', timeStyle: 'short'
  }).format(new Date());

  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const margem = 14;
  const larguraPagina = doc.internal.pageSize.getWidth();
  const alturaPagina  = doc.internal.pageSize.getHeight();
  const inicioTexto = logoDataUrl ? margem + 18 : margem;

  const cabecalho = colunas.map(c => c.label ?? c.key);
  const linhas = dados.map(row => colunas.map(c => row[c.key] ?? ''));

  autoTable(doc, {
    head: [cabecalho],
    body: linhas,
    startY: 28,
    margin: { top: 28, left: margem, right: margem, bottom: 16 },
    styles: { fontSize: 8, cellPadding: 2 },
    headStyles: { fillColor: [22, 27, 34] },
    didDrawPage: () => {
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
    },
  });

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

  const nomeArquivo = `${titulo.replace(/[^a-zA-Z0-9]+/g, '_')}.pdf`;
  doc.save(nomeArquivo);
}
