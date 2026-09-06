import assert from "node:assert/strict";
import test from "node:test";

import { formatHuman, parseArgs, runReleaseCheck } from "./check-remote-release.mjs";

function response(status, payload = null) {
  return new Response(payload === null ? "" : JSON.stringify(payload), {
    status,
    headers: payload === null ? {} : { "content-type": "application/json" },
  });
}

const commit = "a".repeat(40);
const repositoryApi = "https://api.github.com/repos/k8w98rr595-blip/academic-writing-agent";
function workflowRoutes(overrides = {}) {
  return {
    [repositoryApi + "/commits/main"]: response(200, { sha: commit }),
    ...Object.fromEntries(["pages.yml", "production-smoke.yml"].map(workflow => [
      repositoryApi + `/actions/workflows/${workflow}/runs?branch=main&per_page=1`,
      response(200, { workflow_runs: [{ status: "completed", conclusion: "success", head_sha: commit, head_branch: "main", path: `.github/workflows/${workflow}`, ...overrides }] }),
    ])),
  };
}

function routeFetch(routes) {
  return async (url) => {
    const route = routes[String(url)];
    if (!route) throw new Error(`Unexpected URL: ${url}`);
    return route;
  };
}

test("parseArgs rejects unsafe production URLs", () => {
  assert.throws(() => parseArgs(["--backend-url", "http://example.com"]), /must use HTTPS/);
  assert.throws(() => parseArgs(["--pages-url", "https://example.com/?token=secret"]), /must not contain/);
  assert.throws(() => parseArgs(["--expected-requires-totp", "no"]), /must be true or false/);
});

test("private repository produces explicit identity-gate blockers", async () => {
  const options = parseArgs([]);
  const result = await runReleaseCheck(options, {
    fetchImpl: routeFetch({
      "https://api.github.com/repos/k8w98rr595-blip/academic-writing-agent": response(404, { message: "Not Found" }),
      "https://k8w98rr595-blip.github.io/academic-writing-agent/": response(404),
    }),
  });
  assert.equal(result.productionReady, false);
  assert.deepEqual(result.blockers, ["repository_not_public", "pages_unavailable", "backend_not_configured"]);
  assert.match(formatHuman(result), /Repository\s+\[WAIT\]/);
});

test("public Pages and hardened Mock backend produce a ready release", async () => {
  const options = parseArgs(["--backend-url", "https://paperlight.example.com"]);
  const result = await runReleaseCheck(options, {
    fetchImpl: routeFetch({
      "https://api.github.com/repos/k8w98rr595-blip/academic-writing-agent": response(200, {
        private: false,
        visibility: "public",
      }),
      ...workflowRoutes(),
      "https://k8w98rr595-blip.github.io/academic-writing-agent/": response(200),
      "https://paperlight.example.com/api/health": response(200, {
        ok: true,
        providerMode: { detector: "mock", rewrite: "mock" },
      }),
      "https://paperlight.example.com/api/v1/auth/status": response(200, {
        configured: true,
        requiresTotp: false,
      }),
      "https://paperlight.example.com/api/v1/documents": response(401),
    }),
  });
  assert.equal(result.frontendReady, true);
  assert.equal(result.backend.ok, true);
  assert.equal(result.productionReady, true);
  assert.deepEqual(result.blockers, []);
});

test("detector and rewrite modes can be audited independently", async () => {
  const options = parseArgs([
    "--backend-url",
    "https://paperlight.example.com",
    "--expected-detector-mode",
    "mock",
    "--expected-rewrite-mode",
    "deepseek",
    "--expected-requires-totp",
    "false",
  ]);
  const result = await runReleaseCheck(options, {
    fetchImpl: routeFetch({
      "https://api.github.com/repos/k8w98rr595-blip/academic-writing-agent": response(200, {
        private: false,
        visibility: "public",
      }),
      ...workflowRoutes(),
      "https://k8w98rr595-blip.github.io/academic-writing-agent/": response(200),
      "https://paperlight.example.com/api/health": response(200, {
        ok: true,
        providerMode: { detector: "mock", rewrite: "deepseek" },
      }),
      "https://paperlight.example.com/api/v1/auth/status": response(200, {
        configured: true,
        requiresTotp: false,
      }),
      "https://paperlight.example.com/api/v1/documents": response(401),
    }),
  });
  assert.equal(result.backend.ok, true);
  assert.equal(result.backend.auth.expectedRequiresTotp, false);
  assert.equal(result.productionReady, true);
});

for (const [name, change] of [
  ["staging branch", { head_branch: "codex/local-staging" }],
  ["old commit", { head_sha: "b".repeat(40) }],
  ["wrong workflow", { path: ".github/workflows/local-staging.yml" }],
  ["in progress", { status: "in_progress", conclusion: null }],
  ["failed run", { conclusion: "failure" }],
]) {
  test(`rejects ${name} as production release evidence`, async () => {
    const result = await runReleaseCheck(parseArgs([]), { fetchImpl: routeFetch({
      [repositoryApi]: response(200, { private: false, visibility: "public" }),
      ...workflowRoutes(change),
      "https://k8w98rr595-blip.github.io/academic-writing-agent/": response(200),
    }) });
    assert.equal(result.actions.ok, false);
    assert.equal(result.productionReady, false);
    assert.equal(result.actions.workflows.length, 2);
  });
}
