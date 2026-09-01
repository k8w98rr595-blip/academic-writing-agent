import { access, readdir, readFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import path from "node:path";

const trackedMode = process.argv.includes("--tracked");
const requestedRoot = process.argv.slice(2).find((value) => value !== "--" && value !== "--tracked");
const root = path.resolve(process.cwd(), requestedRoot || "apps/web/out");
if (!trackedMode) await access(root);
const patterns = [
  /sk-[A-Za-z0-9_-]{20,}/,
  /(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}/,
  /whsec_[A-Za-z0-9]{16,}/,
  /(?:gh[opusr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})/,
  /AKIA[0-9A-Z]{16}/,
  /Bearer\s+[A-Za-z0-9._-]{24,}/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /otpauth:\/\/totp\//i,
  /eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/,
  /(?:postgres(?:ql)?|redis|rediss):\/\/[^\s:@/]+:[^\s@/]+@/i,
  /DEEPSEEK_API_KEY[ \t]*=[ \t]*(?![<${])[A-Za-z0-9_-]{16,}/,
  /PANGRAM_API_KEY[ \t]*=[ \t]*(?![<${])[A-Za-z0-9_-]{16,}/,
  /STRIPE_(?:SECRET_KEY|WEBHOOK_SECRET)[ \t]*=[ \t]*(?![<${])\S{16,}/,
  /COPYLEAKS_(?:API_KEY|EMAIL|ACCESS_TOKEN)[ \t]*=[ \t]*(?![<${])\S{16,}/,
  /OWNER_PASSWORD_HASH[ \t]*=[ \t]*\$argon2(?:id|i|d)\$v=\d+\$m=\d+,t=\d+,p=\d+\$[A-Za-z0-9+/]{8,}\$[A-Za-z0-9+/]{16,}/,
  /OWNER_TOTP_SECRET[ \t]*=[ \t]*[A-Z2-7]{16,}/,
  /(?:S3|AWS)_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY)[ \t]*=[ \t]*(?![<${])\S{16,}/,
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

const files = trackedMode
  ? execFileSync("git", ["ls-files", "-z"], { encoding: "utf8" })
      .split("\0")
      .filter(Boolean)
      .map((file) => path.resolve(process.cwd(), file))
  : await walk(root);

for (const file of files) {
  const basename = path.basename(file);
  const isStaticArtifact = /\.(?:html|js|json|txt|css|map)$/.test(file);
  const isTrackedSource = /\.(?:html|js|mjs|cjs|jsx|ts|tsx|json|txt|css|map|py|md|ya?ml|toml|ini|env|example|sh|ps1)$/.test(file)
    || basename === "Dockerfile"
    || basename.startsWith(".env");
  if (!(trackedMode ? isTrackedSource : isStaticArtifact)) continue;
  const content = await readFile(file, "utf8");
  for (const pattern of patterns) {
    if (pattern.test(content)) {
      throw new Error(`Secret scan found a credential-like value: ${path.relative(trackedMode ? process.cwd() : root, file)}`);
    }
  }
}
console.log(trackedMode ? "Tracked source secret scan passed." : "Static artifact secret scan passed.");
