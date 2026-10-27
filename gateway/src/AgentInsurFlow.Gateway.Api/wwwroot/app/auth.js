// Connexion Entra par MSAL (code + PKCE, client public), en redirection : aucune fenêtre surgissante.
// Le choix A ou B ne fait que préremplir l'identifiant (loginHint) ; l'identité vient d'Entra.
/* global msal */

let instance;
let config;

export async function initialiser() {
  config = await (await fetch("config.json")).json();
  instance = new msal.PublicClientApplication({
    auth: { clientId: config.client_id, authority: config.authority, redirectUri: `${location.origin}/app/` },
    cache: { cacheLocation: "sessionStorage" }, // la session ne survit pas à l'onglet
  });
  await instance.initialize();
  const retour = await instance.handleRedirectPromise();
  const compte = retour?.account ?? instance.getActiveAccount() ?? instance.getAllAccounts()[0];
  if (compte) instance.setActiveAccount(compte);
}

export function connecter(compte) {
  return instance.loginRedirect({
    scopes: [config.scopes.underwriting],
    loginHint: config.comptes[compte] || undefined,
    prompt: "select_account",
  });
}

export function deconnecter() {
  return instance.logoutRedirect({ postLogoutRedirectUri: `${location.origin}/app/` });
}

/** Jeton d'accès pour un service ; redirige vers Entra si une interaction est requise. */
export async function jeton(portee, forcer = false) {
  const scopes = [config.scopes[portee]];
  try {
    const r = await instance.acquireTokenSilent({ scopes, account: instance.getActiveAccount(), forceRefresh: forcer });
    return r.accessToken;
  } catch (e) {
    if (e instanceof msal.InteractionRequiredAuthError) await instance.acquireTokenRedirect({ scopes });
    throw e;
  }
}

export function compteCourant() {
  const a = instance.getActiveAccount();
  return a ? { nom: a.name || a.username, oid: a.idTokenClaims?.oid ?? a.localAccountId } : null;
}
