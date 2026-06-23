import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/chat": "http://127.0.0.1:8010",
      "/health": "http://127.0.0.1:8010",
      "/auth": "http://127.0.0.1:8010",
      "/agents": "http://127.0.0.1:8010",
      "/threads": "http://127.0.0.1:8010",
      "/mcp-servers": "http://127.0.0.1:8010",
      "/skills": "http://127.0.0.1:8010"
    }
  }
});
