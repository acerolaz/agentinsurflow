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
 * Durée d'un agent = écart de cree_le avec le rapport précédent ; le premier part du clic (lanceA, ms) s'il est connu.
 */
export function frise(etat, lanceA) {
  const rapports = etat?.rapports ?? [];
  const durees = {};
  rapports.forEach((r, i) => {
    const avant = i > 0 ? Date.parse(rapports[i - 1].cree_le) : lanceA;
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

/** L'état se relit chaque seconde tant que POST …/evaluation est en vol. */
export function doitInterroger(statutReponse, enVol) {
  return enVol;
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

const MESSAGES = {
  EVALUATION_EN_COURS: "Une évaluation est déjà en cours pour ce dossier",
  EVALUATION_EN_ATTENTE: "Une revue est déjà en attente pour ce dossier",
  DOSSIER_DECIDE: "Ce dossier a déjà reçu sa décision",
  AUCUNE_REVUE_EN_ATTENTE: "Aucune proposition n'attend votre validation",
  RELANCES_EPUISEES: "Les trois relances ont déjà été envoyées",
  CONTRAT_NON_ACCEPTE: "Le contrat n'est disponible qu'après acceptation",
  TEXTE_INVALIDE: "Le texte du message est vide ou trop long",
};

/** Message lisible d'une réponse en erreur (ProblemDetails avec un code). */
export function messageProbleme(statut, code) {
  if (statut === 404) return "Contrat introuvable";
  if (statut === 429) return "Trop de requêtes, réessayez dans quelques secondes";
  if (statut === 502 || statut === 503) return "Service temporairement indisponible";
  if (statut === 401) return "Session expirée, reconnectez-vous";
  if (statut === 403) return "Accès refusé";
  return MESSAGES[code] ?? "Une erreur est survenue";
}
