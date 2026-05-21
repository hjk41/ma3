import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/',
  plugins: [react()],
  build: { outDir: 'dist' },
  test: { environment: 'happy-dom', setupFiles: './src/test-setup.ts' },
  server: { proxy: { '/v3': 'http://127.0.0.1:18196', '/v2': 'http://127.0.0.1:18196', '/libraries': 'http://127.0.0.1:18196', '/auth': 'http://127.0.0.1:18196', '/healthz': 'http://127.0.0.1:18196' } },
});
