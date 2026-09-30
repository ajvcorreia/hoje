/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const target = process.env.VITE_API_PROXY ?? 'http://localhost:8000';

// SSE-friendly: no timeouts, and the response is streamed through untouched.
const proxy = {
  target,
  changeOrigin: false,
  timeout: 0,
  proxyTimeout: 0,
} as const;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': proxy,
      '/healthz': proxy,
      '/readyz': proxy,
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    // Strict CSP (script-src 'self'; style-src 'self'): never inline assets or CSS.
    assetsInlineLimit: 0,
    cssCodeSplit: false,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    globals: true,
  },
});
