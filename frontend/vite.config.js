import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    // Generates the web app manifest + a service worker so the app is installable
    // and its shell loads offline.
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'Adaptive Nutrition Coach',
        short_name: 'Coach',
        description: 'Calorie targets that adapt to your real metabolism, plus a weekly workout plan.',
        theme_color: '#15803d',
        background_color: '#f7f7f5',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Never cache API calls; data must always be fresh.
        navigateFallbackDenylist: [/^\/api/],
      },
    }),
  ],
  server: {
    // During development, forward /api calls to the FastAPI server.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
