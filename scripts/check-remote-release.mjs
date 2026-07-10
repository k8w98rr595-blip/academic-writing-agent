import { pathToFileURL } from "node:url";

const DEFAULTS = {
  repository: "k8w98rr595-blip/academic-writing-agent",
  pagesUrl: "https://k8w98rr595-blip.github.io/academic-writing-agent/",
  backendUrl: "",
  expectedProviderMode: "mock",
  json: false,
};

function takeValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

export function parseArgs(argv) {
  const options = { ...DEFAULTS };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--repo") {
      options.repository = takeValue(argv, index, flag);
      index += 1;
    } else if (flag === "--pages-url") {
      options.pagesUrl = takeValue(argv, index, flag);
      index += 1;
    } else if (flag === "--backend-url") {
      options.backendUrl = takeValue(argv, index, flag);
      index += 1;
    } else if (flag === "--expected-provider-mode") {
      options.expectedProviderMode = takeValue(argv, index, flag);
      index += 1;
    } else if (flag === "--json") {
      options.json = true;
    } else if (flag === "--help") {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${flag}`);
    }
  }
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(options.repository)) {
    throw new Error("--repo must use owner/repository format");
  }
  options.pagesUrl = normalizeProductionUrl(options.pagesUrl, "--pages-url");
  if (options.backendUrl) {
    options.backendUrl = normalizeProductionUrl(options.backendUrl, "--backend-url");
  }
  return options;
}

export function normalizeProductionUrl(value, flag) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${flag} must be an absolute HTTPS URL`);
  }
  if (parsed.protocol !== "https:") {
    throw new Error(`${flag} must use HTTPS`);
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error(`${flag} must not contain credentials, query parameters, or fragments`);
  }
  return parsed.toString().replace(/\/$/, "");
}

async function request(fetchImpl, url, { json = false, timeoutMs = 20_000 } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(url, {
      redirect: "follow",
      signal: controller.signal,
      headers: {
        Accept: json ? "application/vnd.github+json, application/json" : "text/html, application/json",
        "User-Agent": "Paperlight-release-check/1.0",
      },
    });
    let payload = null;
    if (json) {
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
    }
    return { ok: response.ok, status: response.status, payload };
  } catch (error) {
    return {
      ok: false,
      status: null,
      error: error?.name === "AbortError" ? "timeout" : "network_error",
    };
  } finally {
    clearTimeout(timeout);
  }
}

function endpoint(baseUrl, path) {
  return new URL(path, `${baseUrl}/`).toString();
}

export async function runReleaseCheck(options, { fetchImpl = fetch } = {}) {
  const checkedAt = new Date().toISOString();
  const repositoryApi = `https://api.github.com/repos/${options.repository}`;
  const repositoryResponse = await request(fetchImpl, repositoryApi, { json: true });
  const repositoryPublic =
    repositoryResponse.status === 200 &&
    repositoryResponse.payload?.private === false &&
    repositoryResponse.payload?.visibility === "public";

  let actions = {
    ok: false,
    status: null,
    conclusion: null,
    url: null,
    code: repositoryPublic ? "actions_unavailable" : "repository_not_public",
  };
  if (repositoryPublic) {
    const actionsResponse = await request(fetchImpl, `${repositoryApi}/actions/runs?per_page=1`, { json: true });
    const latest = actionsResponse.payload?.workflow_runs?.[0] ?? null;
    actions = {
      ok: actionsResponse.status === 200 && latest?.conclusion === "success",
      status: actionsResponse.status,
      conclusion: latest?.conclusion ?? null,
      url: latest?.html_url ?? null,
      code:
        actionsResponse.status !== 200
          ? "actions_unavailable"
          : latest?.conclusion === "success"
            ? null
            : latest
              ? "actions_not_successful"
              : "actions_missing",
    };
  }

  const pagesResponse = await request(fetchImpl, `${options.pagesUrl}/`);
  const pages = {
    ok: pagesResponse.status === 200,
    status: pagesResponse.status,
    url: `${options.pagesUrl}/`,
    code: pagesResponse.status === 200 ? null : "pages_unavailable",
  };

  let backend = {
    configured: false,
    ok: false,
    url: null,
    health: null,
    auth: null,
    unauthenticatedDocumentsStatus: null,
    code: "backend_not_configured",
  };
  if (options.backendUrl) {
    const healthResponse = await request(fetchImpl, endpoint(options.backendUrl, "/api/health"), { json: true });
    const authResponse = await request(fetchImpl, endpoint(options.backendUrl, "/api/v1/auth/status"), { json: true });
    const documentsResponse = await request(fetchImpl, endpoint(options.backendUrl, "/api/v1/documents"));
    const providerMode = healthResponse.payload?.providerMode;
    const providerModeOk =
      providerMode?.detector === options.expectedProviderMode &&
      providerMode?.rewrite === options.expectedProviderMode;
    const healthOk = healthResponse.status === 200 && healthResponse.payload?.ok === true && providerModeOk;
    const authOk =
      authResponse.status === 200 &&
      authResponse.payload?.configured === true &&
      authResponse.payload?.requiresTotp === true;
    const boundaryOk = documentsResponse.status === 401;
    backend = {
      configured: true,
      ok: healthOk && authOk && boundaryOk,
      url: options.backendUrl,
      health: {
        status: healthResponse.status,
        ok: healthResponse.payload?.ok === true,
        providerMode: providerMode ?? null,
      },
      auth: {
        status: authResponse.status,
        configured: authResponse.payload?.configured === true,
        requiresTotp: authResponse.payload?.requiresTotp === true,
      },
      unauthenticatedDocumentsStatus: documentsResponse.status,
      code:
        healthResponse.status !== 200
          ? "backend_health_unavailable"
          : !providerModeOk
            ? "backend_provider_mode_mismatch"
            : !authOk
              ? "backend_owner_not_ready"
              : !boundaryOk
                ? "backend_auth_boundary_failed"
                : null,
    };
  }

  const repository = {
    ok: repositoryPublic,
    status: repositoryResponse.status,
    visibility: repositoryResponse.payload?.visibility ?? null,
    url: `https://github.com/${options.repository}`,
    code: repositoryPublic ? null : "repository_not_public",
  };
  const frontendReady = repository.ok && actions.ok && pages.ok;
  const productionReady = frontendReady && backend.ok;
  const blockers = [repository.code, actions.code, pages.code, backend.code].filter(Boolean);

  return {
    checkedAt,
    repository,
    actions,
    pages,
    backend,
    frontendReady,
    productionReady,
    blockers: [...new Set(blockers)],
  };
}

export function formatHuman(result) {
  const mark = (ok) => (ok ? "PASS" : "WAIT");
  const lines = [
    `Repository  [${mark(result.repository.ok)}] status=${result.repository.status ?? "network-error"} visibility=${result.repository.visibility ?? "not-public"}`,
    `Actions     [${mark(result.actions.ok)}] status=${result.actions.status ?? "unavailable"} conclusion=${result.actions.conclusion ?? "none"}`,
    `Pages       [${mark(result.pages.ok)}] status=${result.pages.status ?? "network-error"} ${result.pages.url}`,
    `Backend     [${mark(result.backend.ok)}] ${result.backend.configured ? result.backend.url : "--backend-url not supplied"}`,
    `Production  [${mark(result.productionReady)}] blockers=${result.blockers.join(",") || "none"}`,
  ];
  return lines.join("\n");
}

function helpText() {
  return [
    "Usage: node scripts/check-remote-release.mjs [options]",
    "",
    "Options:",
    "  --repo owner/name                 GitHub repository",
    "  --pages-url https://...           GitHub Pages URL",
    "  --backend-url https://...         Railway service base URL",
    "  --expected-provider-mode mock     Expected detector and rewrite mode",
    "  --json                            Emit JSON",
    "  --help                            Show this help",
  ].join("\n");
}

async function main() {
  try {
    const options = parseArgs(process.argv.slice(2));
    if (options.help) {
      console.log(helpText());
      return;
    }
    const result = await runReleaseCheck(options);
    console.log(options.json ? JSON.stringify(result, null, 2) : formatHuman(result));
    process.exitCode = result.productionReady ? 0 : 2;
  } catch (error) {
    console.error(`Release check failed: ${error.message}`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
