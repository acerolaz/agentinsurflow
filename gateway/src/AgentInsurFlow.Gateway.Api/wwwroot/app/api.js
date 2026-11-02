// Appels aux routes de la gateway (même origine), avec le jeton du service visé.
import { jeton } from "./auth.js";

function envoyer(methode, chemin, corps, j) {
  const entetes = { Authorization: `Bearer ${j}` };
  if (corps !== undefined) entetes["Content-Type"] = "application/json";
  return fetch(chemin, { method: methode, headers: entetes, body: corps === undefined ? undefined : JSON.stringify(corps) });
}

// Un 401 est réessayé une fois avec un jeton renouvelé ; une coupure réseau rend null, jamais une page bloquée.
async function avecJeton(methode, chemin, corps, portee) {
  try {
    const r = await envoyer(methode, chemin, corps, await jeton(portee));
    return r.status === 401 ? await envoyer(methode, chemin, corps, await jeton(portee, true)) : r;
  } catch (e) {
    if (e instanceof TypeError) return null; // fetch : réseau
    throw e; // redirection MSAL en cours
  }
}

/** Rend {statut, json, entetes} ; une coupure réseau rend le statut 0 (message générique). */
export async function appeler(methode, chemin, { portee, corps } = {}) {
  const r = await avecJeton(methode, chemin, corps, portee);
  if (r === null) return { statut: 0, json: null, entetes: null };
  const texte = await r.text();
  let json = null;
  try {
    json = texte ? JSON.parse(texte) : null;
  } catch {
    json = null; // une page d'erreur HTML (proxy) n'est pas du JSON
  }
  return { statut: r.status, json, entetes: r.headers };
}

/** Fichier binaire : {statut, fichier}, mêmes règles qu'appeler. */
export async function telecharger(chemin, { portee } = {}) {
  const r = await avecJeton("GET", chemin, undefined, portee);
  if (r === null) return { statut: 0, fichier: null };
  return { statut: r.status, fichier: r.status === 200 ? await r.blob() : null };
}
