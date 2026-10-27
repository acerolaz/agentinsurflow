// TU — logique pure de l'espace gestionnaire (#103) : aucune I/O, aucun DOM.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  doitInterroger,
  frise,
  gabaritRelance,
  messageProbleme,
  routeDepuisHash,
  spansAffichables,
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

test("frise : validation en cours puis faite", () => {
  assert.equal(frise({ statut_parcours: "EN_ANALYSE", rapports: [] })[4].statut, "en_cours");
  assert.equal(frise({ statut_parcours: "ACCEPTE", rapports: [] })[4].statut, "fait");
});

test("frise : rien encore", () => {
  assert.deepEqual(frise({ statut_parcours: null, rapports: [] }).map((e) => e.statut), Array(5).fill("a_venir"));
});

test("interrogation : tant que l'évaluation est en vol", () => {
  assert.equal(doitInterroger(null, true), true);
  assert.equal(doitInterroger("EN_PAUSE", false), false);
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
  assert.equal(messageProbleme(502), "Service temporairement indisponible");
  assert.equal(messageProbleme(503), "Service temporairement indisponible");
  assert.equal(messageProbleme(500), "Une erreur est survenue");
});
