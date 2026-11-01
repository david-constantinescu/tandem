import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import { fileURLToPath } from "node:url";

const backend = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.TANDEM_BACKEND ?? "http://127.0.0.1:5050";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // manifestul sta in public/ ca sa poata fi citit fara build; pluginul construieste doar service worker-ul
      manifest: false,
      registerType: "prompt",
      injectRegister: false,
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,webmanifest}"],
        navigateFallback: "/index.html",
        // raspunsurile API (date private) si site-urile demo de rezervari nu trec niciodata prin service worker
        navigateFallbackDenylist: [/^\/api\//, /^\/demo-sites\//],
        cleanupOutdatedCaches: true,
      },
    }),
  ],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", globals: true },
});
