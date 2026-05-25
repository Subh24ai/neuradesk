import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/auth': { target: 'http://localhost:8001', changeOrigin: true },
      '/tickets': { target: 'http://localhost:8001', changeOrigin: true },
      '/admin': { target: 'http://localhost:8001', changeOrigin: true },
      '/orgs': { target: 'http://localhost:8001', changeOrigin: true },
      '/health': { target: 'http://localhost:8001', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8001', ws: true, changeOrigin: true },
    },
  },
})
