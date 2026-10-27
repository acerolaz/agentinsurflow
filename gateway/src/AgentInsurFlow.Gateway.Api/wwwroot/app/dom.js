// Construction du DOM sans innerHTML : tout texte venu d'un service passe par textContent.
import { messageProbleme } from "./logique.js";

/** el("a", {href: "#/x", class: "lien"}, "texte", autreNoeud) ; attribut à null/false = absent. */
export function el(balise, attributs = {}, ...enfants) {
  const n = document.createElement(balise);
  for (const [cle, valeur] of Object.entries(attributs)) {
    if (cle.startsWith("on")) n.addEventListener(cle.slice(2), valeur);
    else if (valeur === true) n.setAttribute(cle, "");
    else if (valeur !== null && valeur !== false && valeur !== undefined) n.setAttribute(cle, String(valeur));
  }
  for (const e of enfants.flat()) if (e !== null && e !== undefined && e !== false) n.append(e instanceof Node ? e : String(e));
  return n;
}

/** Message d'erreur annoncé (role="alert") pour une réponse {statut, json}. */
export function erreur(r) {
  return el("p", { class: "erreur", role: "alert" }, messageProbleme(r.statut, r.json?.code));
}

/** Remplace le contenu d'un nœud. */
export function remplir(noeud, ...enfants) {
  noeud.replaceChildren(...enfants.flat().filter((e) => e !== null && e !== undefined && e !== false));
}
