import { writable, derived } from 'svelte/store';

function safeGet(key, fallback) {
    if (typeof localStorage === 'undefined') return fallback;
    try { return JSON.parse(localStorage.getItem(key) ?? JSON.stringify(fallback)); }
    catch { return fallback; }
}

export const usuario      = writable(safeGet('usuario', null));
export const empresaAtiva = writable(safeGet('empresaAtiva', null));
export const token        = writable(typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null);
export const menuPaineis  = writable(safeGet('menuPaineis', []));

export const isAdmin = derived(usuario, $u => $u?.role === 'admin');

if (typeof localStorage !== 'undefined') {
    usuario.subscribe(v => localStorage.setItem('usuario', JSON.stringify(v)));
    empresaAtiva.subscribe(v => localStorage.setItem('empresaAtiva', JSON.stringify(v)));
    token.subscribe(v => v ? localStorage.setItem('token', v) : localStorage.removeItem('token'));
    menuPaineis.subscribe(v => localStorage.setItem('menuPaineis', JSON.stringify(v)));
}

export function logout() {
    usuario.set(null);
    empresaAtiva.set(null);
    token.set(null);
    menuPaineis.set([]);
}
