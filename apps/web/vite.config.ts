import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api/harness": {
        target: "http://127.0.0.1:8002",
        changeOrigin: true,
        ws: true,
        rewrite: (p) => p.replace(/^\/api\/harness/, ""),
      },
      "/api/memory": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/memory/, ""),
      },
    },
  },
});
