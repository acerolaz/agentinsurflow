// TU — logique pure de l'espace gestionnaire (#103) : aucune I/O, aucun DOM.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  messageProbleme,
  routeDepuisHash,
  themeInitial,
} from "../../src/AgentInsurFlow.Gateway.Api/wwwroot/app/logique.js";

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
