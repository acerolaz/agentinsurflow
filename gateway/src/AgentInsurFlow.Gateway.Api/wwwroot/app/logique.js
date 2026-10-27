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
