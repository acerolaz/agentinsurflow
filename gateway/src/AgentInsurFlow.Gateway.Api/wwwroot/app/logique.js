// Logique pure de l'espace gestionnaire : ni DOM ni réseau, testée par node --test (gateway/tests/espace).

const NUMERO = /^AIF-\d{4}-\d{6}$/;

/** Vue à afficher depuis le fragment d'URL ; un numéro mal formé retombe sur le portefeuille. */
export function routeDepuisHash(hash) {
  const [, racine, numero, ...reste] = (hash || "").replace(/^#/, "").split("/");
  if (racine === "tchat" && numero === undefined) return { vue: "tchat" };
  if (racine === "dossiers" && numero !== undefined && reste.length === 0 && NUMERO.test(numero)) {
    return { vue: "dossier", numero };
  }
  return { vue: "dossiers" };
}

/** Thème gardé s'il est valide, sinon la préférence du système. */
export function themeInitial(stocke, prefereSombre) {
  if (stocke === "clair" || stocke === "sombre") return stocke;
  return prefereSombre ? "sombre" : "clair";
}

const ETAPES = [
  ["pieces", "Pièces"],
  ["analyste", "Analyste"],
  ["redacteur", "Rédacteur"],
  ["actuaire", "Actuaire"],
];

/**
 * Frise des cinq étapes d'une évaluation depuis l'état lu (GET …/etat).
 * Durée d'un agent = écart de cree_le avec le rapport précédent ; un rapport postérieur au clic (lanceA, ms : lancer
 * ou reprendre) part au plus tôt du clic, la pause ne compte pas ; le premier rapport antérieur au clic n'a pas de durée.
 */
export function frise(etat, lanceA) {
  const rapports = etat?.rapports ?? [];
  const durees = {};
  rapports.forEach((r, i) => {
    const precedent = i > 0 ? Date.parse(rapports[i - 1].cree_le) : undefined;
    const apresClic = lanceA !== undefined && Date.parse(r.cree_le) >= lanceA;
    const avant = apresClic ? Math.max(precedent ?? lanceA, lanceA) : precedent;
    durees[r.agent] = avant === undefined ? null : Math.round(Date.parse(r.cree_le) - avant) / 1000;
  });
  const etapes = ETAPES.map(([agent, libelle]) => ({
    agent, libelle,
    statut: agent in durees ? "fait" : "a_venir",
    duree_s: durees[agent] ?? null,
    rapport: rapports.findLast((r) => r.agent === agent) ?? null,
  }));
  const s = etat?.statut_parcours;
  const validation = s === "ACCEPTE" || s === "REFUSE" ? "fait" : s === "EN_ANALYSE" ? "en_cours" : "a_venir";
  return [...etapes, { agent: "validation", libelle: "Validation (vous)", statut: validation, duree_s: null, rapport: null }];
}

/**
 * État à afficher pendant une nouvelle évaluation : tant que la nouvelle tentative n'a rien écrit, …/etat rend encore la
 * précédente, dont les rapports ne doivent pas passer pour « faits ». tentativeAvant à null : reprise ou simple lecture.
 */
export function etatAffiche(etat, tentativeAvant) {
  return tentativeAvant !== null && etat?.tentative === tentativeAvant ? { ...etat, rapports: [] } : etat;
}

const IDENTIFIANT = /^[A-Za-z0-9_.:-]{1,60}$/;
const sur = (v) => (typeof v === "string" && IDENTIFIANT.test(v) ? v : "?");

/**
 * Spans d'une trace réduits à ce qui s'affiche : outils MCP et agents, par une liste blanche d'attributs
 * (identifiants courts) ; jamais d'attribut libre ni de span de modèle (prompt, sortie).
 */
export function spansAffichables(spans) {
  return (spans ?? []).flatMap((s) => {
    const a = s.attributes ?? {};
    let parts;
    if (s.name === "mcp.outil") parts = [`Outil ${sur(a["mcp.outil"])}`, a["autorisation.decision"], a["resultat.code"]];
    else if (s.name === "invoke_agent") parts = [`Agent ${sur(a["gen_ai.agent.name"])}`, a["insurflow.mode"], a["insurflow.cause"]];
    else return [];
    const nom = parts.filter((p, i) => i === 0 || (p && IDENTIFIANT.test(p))).join(" · ");
    return [{ nom, duree_ms: Number(s.duree_ms) }];
  });
}

export const LIBELLES_PIECES = {
  releve_information: "relevé d'information",
  permis: "permis de conduire",
  carte_grise: "certificat d'immatriculation",
};

/** Mail de relance prérempli (modifiable par le gestionnaire) ; un type inconnu reste tel quel. */
export function gabaritRelance(manquantes) {
  const pieces = manquantes.map((p) => LIBELLES_PIECES[p] ?? p).join(", ");
  return `Bonjour,\n\nPour finaliser l'étude de votre dossier, merci de nous transmettre : ${pieces}.\n\nCordialement,`;
}

const MESSAGES = {
  EVALUATION_EN_COURS: "Une évaluation est déjà en cours pour ce dossier",
  EVALUATION_EN_ATTENTE: "Une revue est déjà en attente pour ce dossier",
  DOSSIER_DECIDE: "Ce dossier a déjà reçu sa décision",
  AUCUNE_REVUE_EN_ATTENTE: "Aucune proposition n'attend votre validation",
  RELANCES_EPUISEES: "Les trois relances ont déjà été envoyées",
  RELANCES_NON_EPUISEES: "Le dossier se classe sans suite après la troisième relance",
  RELANCE_CONCURRENTE: "Une autre relance vient d'être enregistrée : rechargez le dossier",
  CONTRAT_NON_ACCEPTE: "Le contrat n'est disponible qu'après acceptation",
  TEXTE_INVALIDE: "Le texte du message est vide ou trop long",
};

/** Statuts figés : plus d'évaluation, de relance ni de classement (la décision humaine n'est pas réversible). */
export const STATUTS_FIGES = ["ACCEPTE", "REFUSE", "SANS_SUITE"];

/** Fin de parcours (K8) : classable sans suite après la troisième relance, sur un dossier non figé. */
export function classableSansSuite(etat) {
  return (etat?.nb_relances ?? 0) >= 3 && !STATUTS_FIGES.includes(etat?.statut_parcours);
}

/** Message lisible d'une réponse en erreur (ProblemDetails avec un code). */
export function messageProbleme(statut, code) {
  if (statut === 404) return "Contrat introuvable";
  if (statut === 429) return "Trop de requêtes, réessayez dans quelques secondes";
  if (statut === 502 || statut === 503) return "Service temporairement indisponible";
  if (statut === 401) return "Session expirée, reconnectez-vous";
  if (statut === 403) return "Accès refusé";
  return MESSAGES[code] ?? "Une erreur est survenue";
}

/** Recolle deux chunks : le suivant recommence par la fin du précédent puis « \n » (découpage du rag). */
function recoller(precedent, suivant) {
  for (let k = Math.min(precedent.length, suivant.length - 1); k > 0; k--)
    if (suivant[k] === "\n" && precedent.endsWith(suivant.slice(0, k))) return precedent + suivant.slice(k);
  return `${precedent}\n${suivant}`;
}

/**
 * Conditions générales du contrat imprimé : la notice du contrat type (GET /api/documents/{doc_id}), version en vigueur,
 * chunks recollés dans l'ordre, découpée en sections (« ## ») et lignes (« - » = puce). null si rien à afficher.
 */
export function conditionsGenerales(document) {
  const enVigueur = document?.versions?.filter((v) => !v.obsolete).at(-1)?.version;
  const chunks = (document?.chunks ?? []).filter((c) => c.version === enVigueur).sort((a, b) => a.ordre - b.ordre);
  if (!chunks.length) return null;
  const texte = chunks.map((c) => c.texte).reduce(recoller);
  let titre = "";
  const sections = [];
  for (const ligne of texte.split("\n").map((l) => l.trim()).filter(Boolean)) {
    if (ligne.startsWith("## ")) sections.push({ titre: ligne.slice(3), lignes: [] });
    else if (ligne.startsWith("# ")) titre = ligne.slice(2);
    else {
      if (!sections.length) sections.push({ titre: "", lignes: [] });
      const puce = ligne.startsWith("- ");
      sections.at(-1).lignes.push({ puce, texte: puce ? ligne.slice(2) : ligne });
    }
  }
  return { titre, sections };
}
