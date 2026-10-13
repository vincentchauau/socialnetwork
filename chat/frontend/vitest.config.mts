import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@sn": path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../shared/frontend") } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["app/**/*.{ts,tsx}"],
      exclude: ["app/layout.tsx"],
      thresholds: { statements: 90, lines: 90, functions: 85, branches: 80 },
    },
  },
});
