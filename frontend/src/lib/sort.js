export function compararValores(a, b) {
  if (a == null && b == null) return 0;
  if (a == null) return -1;
  if (b == null) return 1;
  if (typeof a === 'boolean' || typeof b === 'boolean') {
    return (a === b) ? 0 : (a ? 1 : -1);
  }
  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }
  return String(a).localeCompare(String(b), 'pt-BR', { sensitivity: 'base' });
}

export function ordenarLista(lista, campo, direcao, extrator = (item, c) => item[c]) {
  if (!campo || !direcao) return lista;
  const copia = [...lista];
  copia.sort((a, b) => {
    const cmp = compararValores(extrator(a, campo), extrator(b, campo));
    return direcao === 'asc' ? cmp : -cmp;
  });
  return copia;
}

export function proximaDirecao(campoClicado, campoAtual, direcaoAtual) {
  if (campoClicado !== campoAtual) return 'asc';
  if (direcaoAtual === 'asc') return 'desc';
  if (direcaoAtual === 'desc') return null;
  return 'asc';
}
