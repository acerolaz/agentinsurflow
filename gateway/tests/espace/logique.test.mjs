// TU — logique pure de l'espace gestionnaire (#103) : aucune I/O, aucun DOM.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  classableSansSuite,
  conditionsGenerales,
  dateEcheance,
  etatAffiche,
  frise,
  gabaritRelance,
  messageProbleme,
  routeDepuisHash,
  spansAffichables,
  tokensEtape,
  themeInitial,
} from "../../src/AgentInsurFlow.Gateway.Api/wwwroot/app/logique.js";

const T0 = "2026-10-27T10:00:00+00:00";
const T1 = "2026-10-27T10:00:03.100+00:00";
const rapport = (agent, cree_le) => ({ agent, mode: "llm", cause: null, trace_id: "t-1", cree_le });

test("frise : deux rapports espacés de 3,1 s", () => {
  const f = frise({ statut_parcours: "EN_COURS", rapports: [rapport("pieces", T0), rapport("analyste", T1)] });
  assert.deepEqual(f.map((e) => e.statut), ["fait", "fait", "a_venir", "a_venir", "a_venir"]);
  assert.deepEqual(f.map((e) => e.libelle), ["Pièces", "Analyste", "Rédacteur", "Actuaire", "Validation (vous)"]);
  assert.equal(f[0].duree_s, null);
  assert.equal(f[1].duree_s, 3.1);
});

test("frise : la première durée part du clic quand il est connu", () => {
  const f = frise({ statut_parcours: "EN_COURS", rapports: [rapport("pieces", T1)] }, Date.parse(T0));
  assert.equal(f[0].duree_s, 3.1);
});

test("frise : après une reprise, ni durée négative ni pause comptée", () => {
  const T2 = "2026-10-27T10:01:00+00:00"; // Reprendre cliqué à T2, une minute après la pause
  const T3 = "2026-10-27T10:01:02.500+00:00";
  const f = frise({ statut_parcours: "EN_COURS", rapports: [rapport("pieces", T0), rapport("analyste", T3)] }, Date.parse(T2));
  assert.equal(f[0].duree_s, null);
  assert.equal(f[1].duree_s, 2.5);
});

test("frise : validation en cours puis faite", () => {
  assert.equal(frise({ statut_parcours: "EN_ANALYSE", rapports: [] })[4].statut, "en_cours");
  assert.equal(frise({ statut_parcours: "ACCEPTE", rapports: [] })[4].statut, "fait");
});

test("frise : rien encore", () => {
  assert.deepEqual(frise({ statut_parcours: null, rapports: [] }).map((e) => e.statut), Array(5).fill("a_venir"));
});

test("ré-évaluation : les rapports de la tentative précédente ne s'affichent pas", () => {
  const ancien = { statut_parcours: "REVUE_HUMAINE", tentative: 1, rapports: [rapport("pieces", T0)] };
  assert.deepEqual(etatAffiche(ancien, 1).rapports, []);
  assert.equal(etatAffiche(ancien, 1).statut_parcours, "REVUE_HUMAINE");
  assert.equal(etatAffiche({ ...ancien, tentative: 2 }, 1).rapports.length, 1); // la nouvelle tentative a écrit
  assert.equal(etatAffiche(ancien, null), ancien); // reprise ou simple lecture
});

test("relance : gabarit avec les libellés des pièces", () => {
  assert.equal(
    gabaritRelance(["releve_information"]),
    "Bonjour,\n\nPour finaliser l'étude de votre dossier, merci de nous transmettre : relevé d'information.\n\nCordialement,",
  );
});

test("relance : un type inconnu s'affiche tel quel", () => {
  assert.match(gabaritRelance(["releve_information", "x_y"]), /relevé d'information, x_y\./);
});

test("détail : outils et agents seulement, par une liste blanche d'attributs", () => {
  const spans = [
    { name: "mcp.outil", duree_ms: 12.5, attributes: { "mcp.outil": "lister_pieces", "autorisation.decision": "allow", "resultat.code": "OK", "numero_contrat": "AIF-1" } },
    { name: "chat gpt-4.1-mini", duree_ms: 900, attributes: { "gen_ai.prompt": "Bonjour Jean Dupont" } },
    { name: "invoke_agent", duree_ms: 1800, attributes: { "gen_ai.agent.name": "pieces", "insurflow.mode": "repli", "insurflow.cause": "llm_ko" } },
    { name: "mcp.outil", duree_ms: 1, attributes: { "mcp.outil": "<img src=x>", "autorisation.decision": "deny" } },
  ];
  assert.deepEqual(spansAffichables(spans), [
    { nom: "Outil lister_pieces · allow · OK", duree_ms: 12.5 },
    { nom: "Agent pieces · repli · llm_ko", duree_ms: 1800 },
    { nom: "Outil ? · deny", duree_ms: 1 },
  ]);
});

test("tokens : spans de l'agent de l'étape seulement (trace partagée), chaînes OTLP comprises ; null sans appel LLM", () => {
  const agent = (nom, entree, sortie) => ({
    name: "invoke_agent",
    attributes: { "gen_ai.agent.name": nom, "gen_ai.usage.input_tokens": entree, "gen_ai.usage.output_tokens": sortie },
  });
  const outil = { name: "mcp.outil", attributes: { "mcp.outil": "lister_pieces" } };
  const trace = [agent("analyste", 1000, 234), outil, agent("analyste", "50", "6"), agent("redacteur", 9, 9)];
  assert.deepEqual(tokensEtape(trace, "analyste"), { entree: 1050, sortie: 240 });
  assert.equal(tokensEtape([outil, { name: "invoke_agent", attributes: { "gen_ai.agent.name": "pieces" } }], "pieces"), null);
  assert.equal(tokensEtape(null, "pieces"), null);
});

test("route : un dossier valide s'ouvre", () => {
  assert.deepEqual(routeDepuisHash("#/dossiers/AIF-2026-000004"), { vue: "dossier", numero: "AIF-2026-000004" });
});

test("route : un numéro hostile retombe sur le portefeuille", () => {
  assert.deepEqual(routeDepuisHash("#/dossiers/<script>"), { vue: "dossiers" });
  assert.deepEqual(routeDepuisHash("#/dossiers/AIF-2026-0000041"), { vue: "dossiers" });
});

test("route : portefeuille, tchat, et défaut", () => {
  assert.deepEqual(routeDepuisHash("#/dossiers"), { vue: "dossiers" });
  assert.deepEqual(routeDepuisHash("#/tchat"), { vue: "tchat" });
  assert.deepEqual(routeDepuisHash(""), { vue: "dossiers" });
  assert.deepEqual(routeDepuisHash("#/inconnu"), { vue: "dossiers" });
});

test("thème : la préférence système à défaut, le choix gardé sinon", () => {
  assert.equal(themeInitial(null, true), "sombre");
  assert.equal(themeInitial(null, false), "clair");
  assert.equal(themeInitial("clair", true), "clair");
  assert.equal(themeInitial("n'importe quoi", false), "clair");
});

test("messages : un texte lisible par statut et code", () => {
  assert.equal(messageProbleme(404), "Contrat introuvable");
  assert.equal(messageProbleme(409, "EVALUATION_EN_COURS"), "Une évaluation est déjà en cours pour ce dossier");
  assert.equal(messageProbleme(429, "TROP_DE_REQUETES"), "Trop de requêtes, réessayez dans quelques secondes");
  assert.equal(messageProbleme(409, "RELANCE_CONCURRENTE"), "Une autre relance vient d'être enregistrée : rechargez le dossier");
  assert.equal(messageProbleme(409, "RELANCES_EPUISEES"), "Les trois relances ont déjà été envoyées");
  assert.equal(messageProbleme(409, "RELANCES_NON_EPUISEES"), "Le dossier se classe sans suite après la troisième relance");
  assert.equal(messageProbleme(502), "Service temporairement indisponible");
  assert.equal(messageProbleme(503), "Service temporairement indisponible");
  assert.equal(messageProbleme(500), "Une erreur est survenue");
});

test("sans suite : seulement après la troisième relance et avant toute décision", () => {
  assert.equal(classableSansSuite(null), false);
  assert.equal(classableSansSuite({ statut_parcours: "REVUE_HUMAINE", nb_relances: 2 }), false);
  assert.equal(classableSansSuite({ statut_parcours: "REVUE_HUMAINE", nb_relances: 3 }), true);
  for (const fige of ["ACCEPTE", "REFUSE", "SANS_SUITE"])
    assert.equal(classableSansSuite({ statut_parcours: fige, nb_relances: 3 }), false);
});

test("conditions générales : chunks recollés sans le recouvrement, titres et puces, version obsolète ignorée", () => {
  const c1 = "# Notice « Tous risques »\nDocument fictif.\n## Garanties\n- Responsabilité civile\n- Vol";
  const c2 = "nsabilité civile\n- Vol\n- Bris de glace\n## Franchises\nÀ la charge de l'assuré.";
  const document = {
    versions: [{ version: "v0", obsolete: true }, { version: "v1", obsolete: false }],
    chunks: [
      { version: "v1", ordre: 1, texte: c2 },
      { version: "v0", ordre: 0, texte: "## Ancienne\n- à ignorer" },
      { version: "v1", ordre: 0, texte: c1 },
    ],
  };

  assert.deepEqual(conditionsGenerales(document), {
    titre: "Notice « Tous risques »",
    sections: [
      { titre: "", lignes: [{ puce: false, texte: "Document fictif." }] },
      { titre: "Garanties", lignes: [
        { puce: true, texte: "Responsabilité civile" }, { puce: true, texte: "Vol" }, { puce: true, texte: "Bris de glace" }] },
      { titre: "Franchises", lignes: [{ puce: false, texte: "À la charge de l'assuré." }] },
    ],
  });
});

test("conditions générales : document absent → null", () => {
  assert.equal(conditionsGenerales(null), null);
  assert.equal(conditionsGenerales({ versions: [], chunks: [] }), null);
});

test("échéance : un an moins un jour, 29 février compris", () => {
  assert.equal(dateEcheance("2026-11-01"), "2027-10-31");
  assert.equal(dateEcheance("2026-01-01"), "2026-12-31");
  assert.equal(dateEcheance("2028-02-29"), "2029-02-28");
});
