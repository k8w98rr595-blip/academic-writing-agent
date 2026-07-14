import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(process.cwd(), "apps/web/out");
await access(root);
const patterns = [
  /sk-[A-Za-z0-9_-]{20,}/,
  /(?:gh[opusr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})/,
  /AKIA[0-9A-Z]{16}/,
  /Bearer\s+[A-Za-z0-9._-]{24,}/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /otpauth:\/\/totp\//i,
  /eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/,
  /(?:postgres(?:ql)?|redis|rediss):\/\/[^\s:@/]+:[^\s@/]+@/i,
  /DEEPSEEK_API_KEY\s*=\s*\S+/,
  /PANGRAM_API_KEY\s*=\s*\S+/,
  /COPYLEAKS_(?:API_KEY|EMAIL)\s*=\s*\S+/,
  /COPYLEAKS_ACCESS_TOKEN\s*=\s*\S+/,
  /OWNER_PASSWORD_HASH\s*=\s*\S+/,
  /OWNER_TOTP_SECRET\s*=\s*\S+/,
  /(?:S3|AWS)_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY)\s*=\s*\S+/,
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
