import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  base: './', // relative asset URLs: the build can be dropped into any AlterVista subfolder
  build: { target: 'es2022' },
});
