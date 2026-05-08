import { copyFile, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = dirname(dirname(fileURLToPath(import.meta.url)));
const distDir = join(rootDir, "dist");
const assetsDir = join(distDir, "assets");

await rm(distDir, { recursive: true, force: true });
await mkdir(assetsDir, { recursive: true });

const result = await Bun.build({
  entrypoints: [join(rootDir, "src", "main.tsx")],
  outdir: assetsDir,
  naming: {
    entry: "app.js",
    chunk: "[name]-[hash].[ext]",
    asset: "[name]-[hash].[ext]",
  },
  target: "browser",
  minify: true,
});

if (!result.success) {
  for (const log of result.logs) {
    console.error(log);
  }
  process.exit(1);
}

await copyFile(join(rootDir, "src", "index.html"), join(distDir, "index.html"));
await copyFile(join(rootDir, "src", "styles.css"), join(assetsDir, "styles.css"));
