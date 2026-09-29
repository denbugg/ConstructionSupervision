import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Сборка кладётся в dist/ и целиком отдаётся статикой из gateway: отдельного
// веб-сервера у интерфейса нет. В разработке /api и /storage (снимки и отчёты,
// ADR-0017) проксируются на тот же gateway, поэтому пути одинаковы в dev и в проде.
const gateway = process.env.VITE_API_PROXY ?? "http://localhost:8080";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Алиасы: @ → src/, @api → сгенерированные типы API. tsconfig о них знает, но резолвит
  // импорты сборщик. Из @api импортируются только типы, в бандл он не попадает.
  resolve: {
    alias: {
      "@api": fileURLToPath(
        new URL("../../packages/ts-api-client/src/index.ts", import.meta.url),
      ),
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: gateway, changeOrigin: true },
      "/storage": { target: gateway, changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
