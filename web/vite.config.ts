import { defineConfig } from 'vite';

declare const process: { env: Record<string, string | undefined> };

// Backend the dev server proxies /ws to. Override with VYBE_SERVER=http://host:port npm run dev
const server = process.env.VYBE_SERVER ?? 'http://localhost:8000';

export default defineConfig({
  server: {
    host: true,
    proxy: {
      '/api/places': { target: server, changeOrigin: true },
      '/ws': { target: server, ws: true, changeOrigin: true },
    },
  },
  build: {
    rolldownOptions: {
      onwarn(warning, defaultHandler) {
        // lucide-react ships "use client" directives, which are meaningless in an SPA bundle.
        if (warning.code === 'MODULE_LEVEL_DIRECTIVE') return;
        defaultHandler(warning);
      },
    },
  },
});
