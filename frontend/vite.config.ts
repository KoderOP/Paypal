import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port: 5173,
      // Dev proxy: the browser talks to /api on the same origin; no backend URL or secrets in client code.
      proxy: { '/api': { target: env.VITE_API_PROXY_TARGET || 'http://localhost:8000', changeOrigin: true } },
    },
  }
})
