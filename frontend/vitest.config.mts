import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@sn": path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../shared/frontend") },
    // shared/frontend has no node_modules of its own: resolve react from this app's install.
    dedupe: ["react", "react-dom"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    exclude: ["**/node_modules/**"],
    // The account and sign-in pages are large and tests type into them with userEvent: with every file running in its
    // own worker, a test occasionally went past the 5 s default (a timeout, not a failed assertion).
    testTimeout: 15_000,
    coverage: {
      provider: "v8",
      include: ["app/**/lib/**", "app/**/hooks/**", "app/**/components/**", "../shared/frontend/api.ts"],
    },
  },
});
