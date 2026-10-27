// Appels aux routes de la gateway (même origine), avec le jeton du service visé.
import { jeton } from "./auth.js";

function envoyer(methode, chemin, corps, j) {
  const entetes = { Authorization: `Bearer ${j}` };
  if (corps !== undefined) entetes["Content-Type"] = "application/json";
  return fetch(chemin, { method: methode, headers: entetes, body: corps === undefined ? undefined : JSON.stringify(corps) });
}

/**
 * Rend {statut, json, entetes} ; un 401 est réessayé une fois avec un jeton renouvelé. Une coupure réseau rend le
 * statut 0 (message générique) : la page ne reste jamais bloquée sur « en cours ».
 */
export async function appeler(methode, chemin, { portee, corps } = {}) {
  let r;
  try {
    r = await envoyer(methode, chemin, corps, await jeton(portee));
    if (r.status === 401) r = await envoyer(methode, chemin, corps, await jeton(portee, true));
  } catch (e) {
    if (e instanceof TypeError) return { statut: 0, json: null, entetes: null }; // fetch : réseau
    throw e; // redirection MSAL en cours
  }
  const texte = await r.text();
  let json = null;
  try {
    json = texte ? JSON.parse(texte) : null;
  } catch {
    json = null; // une page d'erreur HTML (proxy) n'est pas du JSON
  }
  return { statut: r.status, json, entetes: r.headers };
}
