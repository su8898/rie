import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy: the SPA calls same-origin relative paths (/api/... and /healthz)
// which proxy to the RIE FastAPI backend on :8021. This keeps the session
// cookie same-origin (no CORS, no SameSite friction) with credentials:"include".
const BACKEND = process.env.VITE_API_TARGET ?? "http://localhost:8021";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/healthz": { target: BACKEND, changeOrigin: true },
    },
  },
});
