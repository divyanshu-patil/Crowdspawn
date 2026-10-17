import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // One reused thread: vitest gives each worker 5s to start, and per-file forks miss that on a busy CI runner.
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    pool: "threads",
    maxWorkers: 1,
    isolate: false,
  },
});
