// Appels aux routes de la gateway (même origine), avec le jeton du service visé.
import { jeton } from "./auth.js";

function envoyer(methode, chemin, corps, j) {
  const entetes = { Authorization: `Bearer ${j}` };
  if (corps !== undefined) entetes["Content-Type"] = "application/json";
  return fetch(chemin, { method: methode, headers: entetes, body: corps === undefined ? undefined : JSON.stringify(corps) });
}

/** Rend {statut, json, entetes} ; un 401 est réessayé une fois avec un jeton renouvelé. */
export async function appeler(methode, chemin, { portee, corps } = {}) {
  let r = await envoyer(methode, chemin, corps, await jeton(portee));
  if (r.status === 401) r = await envoyer(methode, chemin, corps, await jeton(portee, true));
  const texte = await r.text();
  let json = null;
  try {
    json = texte ? JSON.parse(texte) : null;
  } catch {
    json = null; // une page d'erreur HTML (proxy) n'est pas du JSON
  }
  return { statut: r.status, json, entetes: r.headers };
}
