// Vue d'un dossier (#104, #129, #101) : lancer ou reprendre l'évaluation, suivre la frise, mettre en pause,
// valider la proposition, puis afficher le contrat généré. L'état se relit chaque seconde pendant l'évaluation.
import { appeler } from "./api.js";
import { el, erreur, remplir } from "./dom.js";
import { doitInterroger, frise, spansAffichables } from "./logique.js";

const SOUS_ONGLETS = [
  ["detail", "Détail de l'étape"],
  ["pieces", "Pièces manquantes"],
  ["contrat", "Contrat proposé"],
];

export async function afficherDossier(zone, numero) {
  const v = {
    numero, etat: null, contrat: null, enVol: false, lanceA: undefined, ecoule: null,
    message: null, etape: null, sousOnglet: "detail", minuteur: null,
  };
  const chemin = encodeURIComponent(numero);

  async function lireEtat() {
    const r = await appeler("GET", `/api/contrats/${chemin}/etat`, { portee: "underwriting" });
    if (r.statut === 200) v.etat = r.json;
    else v.message = erreur(r);
    return r.statut;
  }

  async function lireContrat() {
    const r = await appeler("GET", `/v1/souscriptions/${chemin}/contrat`, { portee: "underwriting" });
    v.contrat = r.statut === 200 ? r.json : null;
  }

  // --- actions -----------------------------------------------------------------------------------
  async function lancer() {
    if (v.enVol) return; // double clic : un seul appel part
    v.enVol = true;
    v.message = null;
    v.lanceA = Date.now();
    rendre();
    v.minuteur = setInterval(async () => {
      if (!zone.isConnected) return clearInterval(v.minuteur); // vue quittée
      v.ecoule = Math.round((Date.now() - v.lanceA) / 1000);
      if (doitInterroger(null, v.enVol)) await lireEtat();
      if (v.enVol) rendre();
    }, 1000);
    const r = await appeler("POST", `/v1/souscriptions/${chemin}/evaluation`, { portee: "cluster" });
    clearInterval(v.minuteur);
    v.enVol = false;
    v.ecoule = Math.round((Date.now() - v.lanceA) / 1000);
    if (r.statut !== 200) v.message = erreur(r);
    else if (r.json.statut === "REVUE_HUMAINE") v.message = el("p", { role: "status" }, r.json.message ?? "Ce dossier nécessite une revue humaine.");
    else if (r.json.statut === "EN_PAUSE") v.message = el("p", { role: "status" }, "Évaluation en pause : « Reprendre » repart de l'étape suivante.");
    await lireEtat();
    if (r.json?.statut === "EN_ANALYSE") v.sousOnglet = "contrat";
    rendre();
  }

  async function pause() {
    const r = await appeler("POST", `/v1/souscriptions/${chemin}/pause`, { portee: "cluster" });
    v.message = r.statut === 202
      ? el("p", { role: "status" }, "Pause demandée : l'évaluation s'arrêtera après l'étape en cours.")
      : erreur(r);
    rendre();
  }

  async function reviser(decision, validation, motif) {
    const r = await appeler("POST", `/v1/souscriptions/${chemin}/revue`, { portee: "cluster", corps: { decision, validation, motif } });
    if (r.statut !== 200) {
      v.message = erreur(r);
      return rendre();
    }
    v.message = el("p", { role: "status" }, decision === "ACCEPTE" ? "Proposition validée : contrat généré." : "Dossier refusé.");
    await lireEtat();
    if (r.json.statut === "ACCEPTE") await lireContrat();
    rendre();
  }

  async function afficherTraces(etape, cible) {
    remplir(cible, el("p", { "aria-busy": "true" }, "Lecture de la trace…"));
    const r = await appeler("GET", `/api/traces/${encodeURIComponent(etape.rapport.trace_id)}`, { portee: "underwriting" });
    if (r.statut !== 200) return remplir(cible, erreur(r));
    const spans = spansAffichables(r.json);
    remplir(cible, spans.length
      ? el("ul", {}, spans.map((s) => el("li", {}, `${s.nom} — ${Math.round(s.duree_ms)} ms`)))
      : el("p", { class: "discret" }, "Aucun span d'outil pour cette étape."));
  }

  // --- rendu -------------------------------------------------------------------------------------
  function statut() {
    return v.etat?.statut_parcours ?? null;
  }

  function barreActions() {
    const s = statut();
    const reprendre = s === "EN_PAUSE";
    const bloque = v.enVol || ["EN_ANALYSE", "ACCEPTE", "REFUSE"].includes(s);
    const derniere = v.etat?.rapports?.at(-1);
    return el("div", { class: "actions" },
      el("button", { type: "button", id: "lancer", "aria-disabled": String(bloque), onclick: () => !bloque && lancer() },
        v.enVol ? "Évaluation en cours…" : reprendre ? "Reprendre" : "Lancer l'évaluation"),
      el("button", { type: "button", id: "pause", class: "secondaire", "aria-disabled": String(!v.enVol), onclick: () => v.enVol && pause() }, "Pause"),
      el("span", { class: "discret", "aria-live": "off" }, v.ecoule === null ? "" : `Temps écoulé : ${v.ecoule} s`),
      derniere ? el("span", { class: "discret" }, "trace_id : ", el("code", {}, derniere.trace_id)) : null);
  }

  function rendreFrise() {
    const etapes = frise(v.etat, v.lanceA);
    return el("ol", { class: "frise", "aria-label": "Étapes de l'évaluation" }, etapes.map((e) =>
      el("li", { class: `etape ${e.statut}` },
        el("button", {
          type: "button", id: `etape-${e.agent}`, class: "secondaire", "aria-pressed": String(v.etape === e.agent),
          "aria-disabled": String(!e.rapport),
          onclick: () => {
            if (!e.rapport) return;
            v.etape = e.agent;
            v.sousOnglet = "detail";
            rendre();
          },
        },
        el("span", { class: "libelle" }, e.libelle),
        el("span", { class: "discret" }, { fait: "fait", en_cours: "en cours", a_venir: "à venir" }[e.statut]
          + (e.duree_s === null ? "" : ` · ${e.duree_s.toFixed(1)} s`))))));
  }

  function panneauDetail() {
    const e = frise(v.etat, v.lanceA).find((x) => x.agent === v.etape);
    if (!e?.rapport) return el("p", { class: "discret" }, "Choisissez une étape terminée dans la frise.");
    const cible = el("div", {});
    return el("div", {},
      el("dl", {},
        el("dt", {}, "Étape"), el("dd", {}, e.libelle),
        el("dt", {}, "Mode"), el("dd", {}, e.rapport.mode === "llm" ? "Agent (LLM)" : "Repli déterministe"),
        el("dt", {}, "Cause"), el("dd", {}, e.rapport.cause ?? "—"),
        el("dt", {}, "Durée"), el("dd", {}, e.duree_s === null ? "—" : `${e.duree_s.toFixed(1)} s`),
        el("dt", {}, "trace_id"), el("dd", {}, el("code", {}, e.rapport.trace_id))),
      el("button", { type: "button", class: "secondaire", onclick: () => afficherTraces(e, cible) }, "Outils appelés"),
      cible);
  }

  function panneauPieces() {
    const pieces = v.etat?.sections?.pieces;
    const manquantes = pieces?.manquantes ?? [];
    if (!pieces) return el("p", { class: "discret" }, "L'agent Pièces n'a pas encore rendu son rapport.");
    if (manquantes.length === 0) return el("p", {}, "Toutes les pièces exigées sont présentes.");
    return el("div", { id: "relance" },
      el("p", {}, "Pièces manquantes :"),
      el("ul", {}, manquantes.map((p) => el("li", {}, p))));
  }

  function liste(titre, valeurs) {
    return valeurs?.length ? [el("dt", {}, titre), el("dd", {}, el("ul", {}, valeurs.map((x) => el("li", {}, x))))] : [];
  }

  function panneauContrat() {
    if (v.contrat) return contratGenere();
    const fiche = v.etat?.sections?.fiche;
    const prime = v.etat?.sections?.prime;
    if (!fiche) return el("p", { class: "discret" }, "Aucune proposition pour l'instant.");
    const enAttente = statut() === "EN_ANALYSE";
    return el("div", {},
      el("dl", {},
        el("dt", {}, "Décision proposée"), el("dd", {}, fiche.decision),
        el("dt", {}, "Type de contrat"), el("dd", {}, fiche.contrat_type || "—"),
        el("dt", {}, "Règles"), el("dd", {}, (fiche.regle_ids ?? []).join(", ") || "—"),
        ...liste("Motifs", fiche.motifs),
        ...liste("Citations", fiche.citations),
        ...(prime ? [el("dt", {}, "Prime"), el("dd", {}, `${prime.prime_ttc_annuelle} € par an, soit ${prime.prime_mensuelle} € par mois`)] : [])),
      enAttente ? formulaireRevue() : null);
  }

  function formulaireRevue() {
    const motif = el("textarea", { id: "motif", name: "motif", rows: "3", minlength: "1", maxlength: "500", required: true });
    const bouton = (texte, decision, validation, classe) =>
      el("button", { type: "submit", class: classe, "data-decision": decision, "data-validation": validation }, texte);
    return el("form", {
      class: "revue",
      onsubmit: (e) => {
        e.preventDefault();
        const b = e.submitter;
        const texte = motif.value.trim();
        if (!texte || !b) return motif.focus();
        e.currentTarget.querySelectorAll("button").forEach((x) => { x.disabled = true; });
        reviser(b.dataset.decision, b.dataset.validation, texte);
      },
    },
    el("label", { for: "motif" }, "Motif de votre décision (obligatoire, 500 caractères au plus)"),
    motif,
    el("div", { class: "actions" },
      bouton("Valider", "ACCEPTE", "VALIDEE"),
      bouton("Corriger et accepter", "ACCEPTE", "CORRIGEE", "secondaire"),
      bouton("Refuser", "REFUSE", "VALIDEE", "secondaire")));
  }

  function contratGenere() {
    const c = v.contrat;
    return el("article", { class: "contrat-imprimable", "aria-labelledby": "titre-contrat" },
      el("h2", { id: "titre-contrat" }, `Contrat ${c.numero_contrat}`),
      el("dl", {},
        el("dt", {}, "Formule"), el("dd", {}, c.formule),
        el("dt", {}, "Type"), el("dd", {}, c.contrat_type),
        el("dt", {}, "Date d'effet"), el("dd", {}, c.date_effet),
        el("dt", {}, "Prime"), el("dd", {}, `${c.prime_ttc_annuelle} € par an, soit ${c.prime_mensuelle} € par mois`),
        el("dt", {}, "Barème / formule"), el("dd", {}, `${c.version_bareme} / ${c.version_formule}`),
        ...liste("Motifs", c.motifs),
        ...liste("Citations", c.citations),
        el("dt", {}, "Validé le"), el("dd", {}, new Date(c.valide_le).toLocaleString("fr-FR"))),
      el("button", { type: "button", class: "ne-pas-imprimer", onclick: () => window.print() }, "Imprimer"));
  }

  function sousOnglets() {
    const nb = v.etat?.sections?.pieces?.manquantes?.length ?? 0;
    const panneaux = { detail: panneauDetail, pieces: panneauPieces, contrat: panneauContrat };
    const onglets = SOUS_ONGLETS.map(([cle, titre]) =>
      el("button", {
        type: "button", role: "tab", id: `sous-${cle}`, "aria-controls": "sous-panneau",
        "aria-selected": String(v.sousOnglet === cle), tabindex: v.sousOnglet === cle ? "0" : "-1",
        onclick: () => {
          v.sousOnglet = cle;
          rendre();
          document.getElementById(`sous-${cle}`)?.focus();
        },
      }, titre, cle === "pieces" && nb ? el("span", { class: "pastille", "aria-label": `${nb} manquante(s)` }, String(nb)) : null));
    return [
      el("div", {
        role: "tablist", "aria-label": "Détail du dossier", class: "sous-onglets",
        onkeydown: (e) => {
          if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
          const i = SOUS_ONGLETS.findIndex(([cle]) => cle === v.sousOnglet);
          const pas = e.key === "ArrowRight" ? 1 : SOUS_ONGLETS.length - 1;
          v.sousOnglet = SOUS_ONGLETS[(i + pas) % SOUS_ONGLETS.length][0];
          rendre();
          document.getElementById(`sous-${v.sousOnglet}`)?.focus();
        },
      }, onglets),
      el("section", { id: "sous-panneau", role: "tabpanel", "aria-labelledby": `sous-${v.sousOnglet}` }, panneaux[v.sousOnglet]()),
    ];
  }

  function rendre() {
    if (!zone.isConnected) return;
    const s = statut();
    const focus = document.activeElement?.id; // le rendu toutes les secondes ne doit pas voler le focus clavier
    remplir(zone,
      el("p", { class: "ne-pas-imprimer" }, el("a", { href: "#/dossiers" }, "← Mes dossiers")),
      el("h1", {}, `Dossier ${numero}`),
      el("p", { class: "discret" }, s ? `Statut : ${s} · tentative ${v.etat.tentative}` : "Jamais évalué"),
      barreActions(),
      v.message,
      rendreFrise(),
      sousOnglets());
    if (focus) document.getElementById(focus)?.focus();
  }

  remplir(zone, el("h1", {}, `Dossier ${numero}`), el("p", { "aria-busy": "true" }, "Chargement…"));
  if ((await lireEtat()) !== 200) return remplir(zone, el("p", {}, el("a", { href: "#/dossiers" }, "← Mes dossiers")), v.message);
  if (statut() === "ACCEPTE") await lireContrat();
  if (statut() === "ACCEPTE" || statut() === "EN_ANALYSE") v.sousOnglet = "contrat";
  rendre();
}
