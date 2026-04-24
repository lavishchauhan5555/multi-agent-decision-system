import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(),tailwindcss()],
   server: {
    port: 5173,
    proxy: {
      // All API traffic → Node.js :3001
      '/api': {
        target:       'http://localhost:3001',
        changeOrigin: true,
      },
      // Health check → Node.js
      '/health': {
        target:       'http://localhost:3001',
        changeOrigin: true,
      },
      // Socket.IO (future use)
      '/socket.io': {
        target:       'http://localhost:3001',
        changeOrigin: true,
        ws:           true,
      },
    },
  },
})
