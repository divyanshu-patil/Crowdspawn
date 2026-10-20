import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // One reused thread keeps start-up cheap. Vitest 4.0.8 gave a worker only 5 s to start, which a busy machine
  // missed ([J1]); 4.0.18 waits 90 s. turbo.json also runs web#test after web#build so next build can't starve it.
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.{ts,tsx}"],
    pool: "threads",
    maxWorkers: 1,
    isolate: false,
  },
});
