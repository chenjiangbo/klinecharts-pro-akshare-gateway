import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  resolve: {
    alias: {
      "@datafeed": resolve(__dirname, "../../packages/datafeed/src"),
    },
  },
  server: {
    fs: {
      allow: [resolve(__dirname, "../..")],
    },
  },
});
