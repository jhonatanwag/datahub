import { writable } from 'svelte/store';

export const empresa  = writable(null);
export const usuario  = writable(null);
export const token    = writable(
  typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null
);
