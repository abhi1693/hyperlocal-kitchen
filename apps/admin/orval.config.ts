import { defineConfig } from "orval";
export default defineConfig({
  admin: {
    input: { target: "../../docs/openapi/admin.json" },
    output: {
      target: "./src/lib/api/generated/admin.ts",
      schemas: "./src/lib/api/generated/models",
      client: "react-query",
      httpClient: "fetch",
      mode: "split",
      clean: true,
      override: {
        mutator: { path: "./src/lib/api/client.ts", name: "adminFetch" },
        fetch: { includeHttpResponseReturnType: false },
        query: { version: 5 },
      },
    },
  },
});
