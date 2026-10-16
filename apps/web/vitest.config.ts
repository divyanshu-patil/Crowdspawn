import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Two test files: two workers is enough, and spare forks time out on a busy machine.
  test: { environment: "jsdom", include: ["tests/**/*.test.{ts,tsx}"], maxWorkers: 2 },
});
