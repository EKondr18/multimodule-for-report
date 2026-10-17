import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Отдельный конфиг для тестов: vite.config.ts (dev-сервер, прокси) не трогаем.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
