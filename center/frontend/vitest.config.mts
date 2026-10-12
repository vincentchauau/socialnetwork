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
      include: ["app/lib/**", "app/hooks/**", "app/components/**", "../../shared/frontend/api.ts"],
    },
  },
});
