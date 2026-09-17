import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const API_ORIGIN = 'http://127.0.0.1:8484'
const DEV_HOST = '127.0.0.1'
const DEV_PORT = 5173

// Built assets are served by `bisect serve` from the Python package.
const STATIC_OUT_DIR = '../agent_bisect/server/static'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: DEV_HOST,
    port: DEV_PORT,
    strictPort: true,
    proxy: { '/api': { target: API_ORIGIN, changeOrigin: false } },
  },
  preview: { host: DEV_HOST, port: DEV_PORT, strictPort: true },
  build: {
    outDir: STATIC_OUT_DIR,
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/components/charts/**', 'src/**/*.test.*', 'src/test/**'],
    },
  },
})
