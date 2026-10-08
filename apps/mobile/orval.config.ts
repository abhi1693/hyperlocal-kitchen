import { readFile, writeFile } from "node:fs/promises";
import { basename } from "node:path";
import { defineConfig } from "orval";

export default defineConfig({
  mobile: {
    input: {
      target: "../../docs/openapi/api.json",
      // Keep every backend schema, without generating HTTP operations.
      override: { transformer: (document) => ({ ...document, paths: {} }) },
    },
    output: {
      // Orval requires a target. Keep its empty metadata file inside generated output.
      target: "./src/api/generated/client.ts",
      schemas: "./src/api/generated",
      // Never let generator cleanup remove application source or native projects.
      clean: false,
      override: { enumGenerationType: "union" },
    },
    hooks: {
      afterAllFilesWrite: async (paths) => {
        // An operation-free client contains only a header; normalize its trailing blank line.
        for (const path of paths as string[]) {
          if (basename(path) === "client.ts") {
            const source = await readFile(path, "utf8");
            await writeFile(path, source.trimEnd() + "\n");
          }
        }
      },
    },
  },
});
