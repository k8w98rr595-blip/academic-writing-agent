import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const publicDir = path.resolve(process.cwd(), "public");
await mkdir(publicDir, { recursive: true });
const apiBaseUrl = String(process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const basePath = String(process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/$/, "");
if (!/^https:\/\//.test(apiBaseUrl) && !/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(apiBaseUrl)) {
  throw new Error("NEXT_PUBLIC_API_BASE_URL must be HTTPS or loopback HTTP");
}
await writeFile(
  path.join(publicDir, "config.js"),
  `window.PAPERLIGHT_CONFIG = Object.freeze(${JSON.stringify({ apiBaseUrl, basePath })});\n`,
  "utf8",
);
