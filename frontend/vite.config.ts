import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		host: true,
		proxy: {
			'/api': { target: 'http://backend:3001', changeOrigin: true }
		}
	}
});
