import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const script = fileURLToPath(new URL("./check-static-secrets.mjs", import.meta.url));

async function runFixture(content) {
  const root = await mkdtemp(path.join(os.tmpdir(), "paperlight-secret-scan-"));
  try {
    await writeFile(path.join(root, "asset.js"), content, "utf8");
    return spawnSync(process.execPath, [script, root], { encoding: "utf8" });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

async function runTrackedFixture(content) {
  const root = await mkdtemp(path.join(os.tmpdir(), "paperlight-source-scan-"));
  try {
    await writeFile(path.join(root, "settings.py"), content, "utf8");
    spawnSync("git", ["init", "--quiet"], { cwd: root, encoding: "utf8" });
    spawnSync("git", ["add", "settings.py"], { cwd: root, encoding: "utf8" });
    return spawnSync(process.execPath, [script, "--tracked"], { cwd: root, encoding: "utf8" });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

test("static scanner rejects Stripe secret and webhook formats", async () => {
  const secret = ["sk", "test", "1234567890abcdefghijkl"].join("_");
  const restricted = ["rk", "live", "1234567890abcdefghijkl"].join("_");
  const webhook = ["whsec", "1234567890abcdefghijkl"].join("_");
  for (const value of [
    secret,
    restricted,
    webhook,
    `STRIPE_SECRET_KEY=${secret}`,
  ]) {
    const result = await runFixture(`window.value=${JSON.stringify(value)};`);
    assert.notEqual(result.status, 0, value);
    assert.match(`${result.stdout}${result.stderr}`, /Secret scan found a credential-like value/);
  }
});

test("static scanner accepts public Stripe Price identifiers", async () => {
  const result = await runFixture("window.price='price_public_catalog_identifier';");
  assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
});

test("tracked source scanner checks non-static source files", async () => {
  const secret = ["sk", "live", "1234567890abcdefghijkl"].join("_");
  const result = await runTrackedFixture(`STRIPE_SECRET_KEY = ${JSON.stringify(secret)}`);
  assert.notEqual(result.status, 0);
  assert.match(`${result.stdout}${result.stderr}`, /settings\.py/);
});
