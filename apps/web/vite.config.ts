import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Сборка кладётся в dist/ и целиком отдаётся статикой из gateway: отдельного
// веб-сервера у интерфейса нет. В разработке /api проксируется на тот же
// gateway, поэтому путь запроса одинаков и в dev, и в проде.
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
      "/api": {
        target: process.env.VITE_API_PROXY ?? "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
