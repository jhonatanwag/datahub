import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		host: true,
		allowedHosts: ['frontend'],
		proxy: {
			'/api': { target: process.env.VITE_PROXY_TARGET || 'http://backend:3001', changeOrigin: true }
		}
	}
});
