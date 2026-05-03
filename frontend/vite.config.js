import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = fileURLToPath(new URL(".", import.meta.url));
const repoRoot = path.resolve(frontendDir, "..");

function normalizeProxyHost(rawHost) {
  const host = String(rawHost || "").trim() || "127.0.0.1";
  return host === "0.0.0.0" ? "127.0.0.1" : host;
}

function resolveApiTarget(env) {
  const explicitApiUrl = String(env.VITE_API_URL || "").trim().replace(/\/+$/, "");
  if (explicitApiUrl) return explicitApiUrl;

  const host = normalizeProxyHost(env.API_HOST);
  const port = String(env.API_PORT || "8765").trim() || "8765";
  return `http://${host}:${port}`;
}

export default defineConfig(({ mode }) => {
  const frontendEnv = loadEnv(mode, frontendDir, "");
  const rootEnv = loadEnv(mode, repoRoot, "");
  const env = { ...rootEnv, ...frontendEnv };
  const apiTarget = resolveApiTarget(env);
  const proxy = {
    "/api": {
      target: apiTarget,
      changeOrigin: true,
    },
  };

  return {
    plugins: [react()],
    envDir: frontendDir,
    envPrefix: ["VITE_"],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("node_modules/react") || id.includes("node_modules/react-dom")) {
              return "react-vendor";
            }

            if (id.includes("node_modules/@supabase")) {
              return "supabase";
            }

            if (id.includes("node_modules/lucide-react")) {
              return "icons";
            }
          },
        },
      },
    },
    server: {
      proxy,
    },
    preview: {
      proxy,
    },
  };
});
