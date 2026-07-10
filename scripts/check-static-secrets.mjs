import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(process.cwd(), "apps/web/out");
await access(root);
const patterns = [
  /sk-[A-Za-z0-9_-]{20,}/,
  /Bearer\s+[A-Za-z0-9._-]{24,}/,
  /DEEPSEEK_API_KEY\s*=\s*\S+/,
  /PANGRAM_API_KEY\s*=\s*\S+/,
  /COPYLEAKS_ACCESS_TOKEN\s*=\s*\S+/,
  /OWNER_PASSWORD_HASH\s*=\s*\S+/,
];

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(target));
    else files.push(target);
  }
  return files;
}

for (const file of await walk(root)) {
  if (!/\.(?:html|js|json|txt|css|map)$/.test(file)) continue;
  const content = await readFile(file, "utf8");
  for (const pattern of patterns) {
    if (pattern.test(content)) throw new Error(`Static artifact may contain a secret: ${path.relative(root, file)}`);
  }
}
console.log("Static artifact secret scan passed.");
