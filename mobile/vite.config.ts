import { defineConfig } from "vite";
import uni from "@dcloudio/vite-plugin-uni";
import path from "node:path";

export default defineConfig({
  plugins: [uni()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src")
    }
  },
  build: {
    sourcemap: false,
    minify: "terser",
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true
      }
    }
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_TARGET || "http://localhost:8000",
        changeOrigin: true
      }
    }
  }
});
