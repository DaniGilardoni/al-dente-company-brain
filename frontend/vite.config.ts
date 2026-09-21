import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../backend/static",
    emptyOutDir: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/ask": "http://localhost:8000",
      "/api": "http://localhost:8000",
      "/files": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
