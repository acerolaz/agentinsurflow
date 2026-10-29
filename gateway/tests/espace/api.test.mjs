// TU — appels de l'espace (api.js) : MSAL et fetch simulés, aucune I/O.
import { test } from "node:test";
import assert from "node:assert/strict";

const APP = "../../src/AgentInsurFlow.Gateway.Api/wwwroot/app";

globalThis.location = { origin: "http://localhost" };
globalThis.msal = {
  InteractionRequiredAuthError: class extends Error {},
  PublicClientApplication: class {
    async initialize() {}
    async handleRedirectPromise() { return null; }
    getActiveAccount() { return null; }
    getAllAccounts() { return []; }
    setActiveAccount() {}
    async acquireTokenSilent({ forceRefresh }) { return { accessToken: forceRefresh ? "renouvele" : "jeton" }; }
  },
};

test("appel : une coupure réseau rend le statut 0 au lieu de bloquer la page", async () => {
  globalThis.fetch = async (url) => {
    if (url === "config.json") return { json: async () => ({ client_id: "c", authority: "a", scopes: { cluster: "s" }, comptes: {} }) };
    throw new TypeError("Failed to fetch");
  };
  await (await import(`${APP}/auth.js`)).initialiser();
  const { appeler } = await import(`${APP}/api.js`);
  const r = await appeler("POST", "/v1/souscriptions/AIF-2026-000001/evaluation", { portee: "cluster" });
  assert.deepEqual(r, { statut: 0, json: null, entetes: null });
});

test("appel : un 401 est rejoué une fois avec un jeton renouvelé", async () => {
  const jetons = [];
  globalThis.fetch = async (url, init) => {
    if (url === "config.json") return { json: async () => ({ client_id: "c", authority: "a", scopes: { cluster: "s" }, comptes: {} }) };
    jetons.push(init.headers.Authorization);
    return jetons.length === 1
      ? { status: 401, text: async () => "", headers: null }
      : { status: 200, text: async () => '{"ok":true}', headers: null };
  };
  await (await import(`${APP}/auth.js`)).initialiser();
  const { appeler } = await import(`${APP}/api.js`);
  const r = await appeler("GET", "/v1/souscriptions/AIF-2026-000001", { portee: "cluster" });
  assert.deepEqual(jetons, ["Bearer jeton", "Bearer renouvele"]);
  assert.deepEqual(r, { statut: 200, json: { ok: true }, entetes: null });
});
