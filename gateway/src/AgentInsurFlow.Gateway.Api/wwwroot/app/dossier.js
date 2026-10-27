// Vue d'un dossier (#104, #129, #101) : lancer ou reprendre l'évaluation, suivre la frise, mettre en pause,
// valider la proposition, relancer puis classer sans suite, et afficher le contrat généré. L'état se relit chaque
// seconde pendant l'évaluation.
import { appeler } from "./api.js";
import { el, erreur, picto, remplir } from "./dom.js";
import {
  LIBELLES_GARANTIES, LIBELLES_PIECES, PICTOS, STATUTS_FIGES, classableSansSuite, conditionsGenerales, dateEcheance, etatAffiche,
  frise, gabaritRelance,
  spansAffichables, tokensEtape,
} from "./logique.js";

const SOUS_ONGLETS = [
  ["detail", "Détail de l'étape", "detail"],
  ["pieces", "Pièces manquantes", "manquantes"],
  ["contrat", "Contrat proposé", "contrat"],
];

export async function afficherDossier(zone, numero) {
  const v = {
    numero, etat: null, fiche: null, contrat: null, conditions: null, enVol: false, lanceA: undefined, ecoule: null,
    message: null, etape: null, tokens: {}, sousOnglet: "detail", minuteur: null, tentativeAvant: null, motif: "",
  };
  const SUIVI_MAX_S = 120; // rechargement pendant une évaluation : l'état se relit au plus ce temps
  const chemin = encodeURIComponent(numero);

  // Une erreur de lecture de l'état s'efface à la lecture réussie suivante (un 429 ponctuel ne reste pas affiché).
  async function lireEtat() {
    const r = await appeler("GET", `/api/contrats/${chemin}/etat`, { portee: "underwriting" });
    if (r.statut === 200) {
      v.etat = r.json;
      if (v.erreurEtat) v.message = null;
      v.erreurEtat = false;
    } else {
      v.message = erreur(r);
      v.erreurEtat = true;
    }
    return r.statut;
  }

  const ecoule = () => Math.round((Date.now() - v.lanceA) / 1000);

  /** Relit l'état chaque seconde : pendant POST …/evaluation, ou après un rechargement tant que le statut est EN_COURS. */
  function suivre() {
    clearInterval(v.minuteur);
    const debut = Date.now();
    v.minuteur = setInterval(async () => {
      if (!zone.isConnected) return clearInterval(v.minuteur); // vue quittée
      if (v.enVol) v.ecoule = ecoule();
      await lireEtat();
      if (!v.enVol && (statut() !== "EN_COURS" || Date.now() - debut > SUIVI_MAX_S * 1000)) clearInterval(v.minuteur);
      rendre();
    }, 1000);
  }

  // Fiche du lead (exception du 27/10) : lue une fois, affichée seulement ici, jamais envoyée au cluster.
  async function lireFiche() {
    const r = await appeler("GET", `/api/contrats/${chemin}/souscripteur`, { portee: "underwriting" });
    v.fiche = r.statut === 200 ? r.json : null;
  }

  async function lireContrat() {
    const r = await appeler("GET", `/v1/souscriptions/${chemin}/contrat`, { portee: "underwriting" });
    v.contrat = r.statut === 200 ? r.json : null;
    // Conditions générales : la notice du contrat type, lue au corpus (rag) ; absente, le contrat s'imprime sans elles.
    if (!v.contrat) return;
    const n = await appeler("GET", `/api/documents/${encodeURIComponent(v.contrat.contrat_type)}`, { portee: "rag" });
    v.conditions = n.statut === 200 ? conditionsGenerales(n.json) : null;
  }

  // --- actions -----------------------------------------------------------------------------------
  async function lancer() {
    if (v.enVol) return; // double clic : un seul appel part
    v.enVol = true;
    v.message = null;
    v.lanceA = Date.now();
    // nouvelle tentative (pas une reprise) : la précédente ne s'affiche pas en attendant la première écriture
    v.tentativeAvant = statut() === "EN_PAUSE" ? null : v.etat?.tentative ?? null;
    rendre();
    suivre();
    const r = await appeler("POST", `/v1/souscriptions/${chemin}/evaluation`, { portee: "cluster" });
    clearInterval(v.minuteur);
    v.enVol = false;
    v.tentativeAvant = null;
    v.ecoule = ecoule();
    if (r.statut !== 200) v.message = erreur(r);
    else if (r.json.statut === "REVUE_HUMAINE") v.message = el("p", { role: "status" }, r.json.message ?? "Ce dossier nécessite une revue humaine.");
    else if (r.json.statut === "EN_PAUSE") v.message = el("p", { role: "status" }, "Évaluation en pause : « Reprendre » repart de l'étape suivante.");
    await lireEtat();
    if (r.json?.statut === "EN_ANALYSE") v.sousOnglet = "contrat";
    rendre();
  }

  async function pause() {
    const r = await appeler("POST", `/v1/souscriptions/${chemin}/pause`, { portee: "cluster" });
    if (r.statut !== 202) v.message = erreur(r);
    else if (r.json?.pause === "ignoree") v.message = el("p", { role: "status" }, "Pause sans effet : plus aucun agent à appeler, l'évaluation se termine.");
    else v.message = el("p", { role: "status" }, "Pause demandée : l'évaluation s'arrêtera après l'étape en cours.");
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

  // Tokens de l'étape : lus une fois dans la trace (span de l'agent), clé trace + agent.
  async function lireTokens(e) {
    const cle = `${e.rapport.trace_id}:${e.agent}`;
    if (cle in v.tokens) return;
    v.tokens[cle] = undefined;
    const r = await appeler("GET", `/api/traces/${encodeURIComponent(e.rapport.trace_id)}`, { portee: "underwriting" });
    v.tokens[cle] = r.statut === 200 ? tokensEtape(r.json, e.agent) : "indisponible";
    rendre();
  }

  function texteTokens(e) {
    const t = v.tokens[`${e.rapport.trace_id}:${e.agent}`];
    if (t === undefined) return "lecture…";
    if (t === null) return "— (aucun appel LLM)";
    if (typeof t === "string") return t;
    const n = (x) => x.toLocaleString("fr-FR");
    return `${n(t.entree + t.sortie)} (entrée ${n(t.entree)}, sortie ${n(t.sortie)})`;
  }

  // --- rendu -------------------------------------------------------------------------------------
  function statut() {
    return v.etat?.statut_parcours ?? null;
  }

  function barreActions() {
    const s = statut();
    const reprendre = s === "EN_PAUSE";
    const bloque = v.enVol || ["EN_ANALYSE", ...STATUTS_FIGES].includes(s);
    const derniere = v.etat?.rapports?.at(-1);
    return el("div", { class: "actions" },
      el("button", { type: "button", id: "lancer", "aria-disabled": String(bloque), onclick: () => !bloque && lancer() },
        picto(PICTOS.lancer), v.enVol ? "Évaluation en cours…" : reprendre ? "Reprendre" : "Lancer l'évaluation"),
      el("button", { type: "button", id: "pause", class: "secondaire", "aria-disabled": String(!v.enVol), onclick: () => v.enVol && pause() }, picto(PICTOS.pause), "Pause"),
      el("span", { class: "discret", "aria-live": "off" }, v.ecoule === null ? "" : `Temps écoulé : ${v.ecoule} s`),
      derniere ? el("span", { class: "discret" }, "trace_id : ", el("code", {}, derniere.trace_id)) : null);
  }

  const etatFrise = () => etatAffiche(v.etat, v.tentativeAvant);

  function rendreFrise() {
    const etapes = frise(etatFrise(), v.lanceA);
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
            lireTokens(e);
          },
        },
        el("span", { class: "libelle" }, picto(PICTOS[e.agent]), e.libelle),
        el("span", { class: "discret" }, { fait: "fait", en_cours: "en cours", a_venir: "à venir" }[e.statut]
          + (e.duree_s === null ? "" : ` · ${e.duree_s.toFixed(1)} s`))))));
  }

  function panneauDetail() {
    const e = frise(etatFrise(), v.lanceA).find((x) => x.agent === v.etape);
    if (!e?.rapport) return el("p", { class: "discret" }, "Choisissez une étape terminée dans la frise.");
    const cible = el("div", {});
    return el("div", {},
      el("dl", {},
        el("dt", {}, "Étape"), el("dd", {}, e.libelle),
        el("dt", {}, "Mode"), el("dd", {}, e.rapport.mode === "llm" ? "Agent (LLM)" : "Repli déterministe"),
        el("dt", {}, "Cause"), el("dd", {}, e.rapport.cause ?? "—"),
        el("dt", {}, "Durée"), el("dd", {}, e.duree_s === null ? "—" : `${e.duree_s.toFixed(1)} s`),
        el("dt", {}, "Tokens"), el("dd", {}, texteTokens(e)),
        el("dt", {}, "trace_id"), el("dd", {}, el("code", {}, e.rapport.trace_id))),
      el("button", { type: "button", class: "secondaire", onclick: () => afficherTraces(e, cible) }, picto(PICTOS.outils), "Outils appelés"),
      cible);
  }

  function manquantes() {
    const pieces = v.etat?.sections?.pieces;
    return pieces?.statut === "incomplet" ? pieces.manquantes ?? [] : [];
  }

  async function envoyerRelance(texte, pieces) {
    v.relanceEnVol = true;
    rendre();
    const r = await appeler("POST", `/api/contrats/${chemin}/relances`, { portee: "underwriting", corps: { texte, pieces } });
    v.relanceEnVol = false;
    if (r.statut === 201) {
      v.relance = { message: el("p", { role: "status" }, `Relance ${r.json.rang}/${r.json.max} enregistrée (envoi par e-mail à partir du 15/11)`), texte };
      await lireEtat();
    } else {
      v.relance = { message: erreur(r), texte: null }; // 409 : épuisées, dossier décidé ou envoi simultané
    }
    rendre();
  }

  async function classerSansSuite() {
    if (!window.confirm("Classer ce dossier sans suite ? La décision est définitive.")) return;
    v.relanceEnVol = true;
    rendre();
    const r = await appeler("POST", `/api/contrats/${chemin}/sans-suite`, { portee: "underwriting" });
    v.relanceEnVol = false;
    v.relance = { message: r.statut === 204 ? el("p", { role: "status" }, "Dossier classé sans suite.") : erreur(r), texte: null };
    if (r.statut === 204) await lireEtat();
    rendre();
  }

  function panneauPieces() {
    if (statut() === "SANS_SUITE")
      return el("div", {}, el("p", {}, `Dossier classé sans suite après ${v.etat.nb_relances ?? 0} relances restées sans réponse.`),
        v.relance?.message ?? null);
    const pieces = v.etat?.sections?.pieces;
    if (!pieces) return el("p", { class: "discret" }, "L'agent Pièces n'a pas encore rendu son rapport.");
    const liste = manquantes();
    if (liste.length === 0) return el("p", {}, "Toutes les pièces exigées sont présentes.");
    const envoyees = v.etat.nb_relances ?? 0;
    const epuisees = envoyees >= 3;
    v.brouillonRelance ??= gabaritRelance(liste);
    const champ = el("textarea", {
      id: "texte-relance", rows: "8", maxlength: "4000", required: true,
      oninput: (e) => { v.brouillonRelance = e.currentTarget.value; },
    });
    champ.value = v.brouillonRelance; // propriété, jamais innerHTML
    return el("div", {},
      el("p", {}, "Pièces manquantes : ", liste.map((p) => LIBELLES_PIECES[p] ?? p).join(", ")),
      el("p", { class: "discret" }, `Relance ${envoyees}/3`),
      el("form", {
        class: "revue",
        onsubmit: (e) => {
          e.preventDefault();
          const texte = champ.value.trim();
          if (texte && !epuisees && !v.relanceEnVol) envoyerRelance(texte, liste);
        },
      },
      el("label", { for: "texte-relance" }, "Message au client (modifiable)"),
      champ,
      el("div", { class: "actions" },
        el("button", { type: "submit", id: "envoyer-relance", "aria-disabled": String(epuisees || !!v.relanceEnVol) },
          picto(PICTOS.relance), epuisees ? "3 relances déjà envoyées" : "Envoyer la relance"),
        classableSansSuite(v.etat)
          ? el("button", { type: "button", id: "sans-suite", class: "secondaire", "aria-disabled": String(!!v.relanceEnVol),
            onclick: () => !v.relanceEnVol && classerSansSuite() }, picto(PICTOS.sans_suite), "Classer sans suite")
          : null)),
      v.relance?.message ?? null,
      v.relance?.texte ? el("blockquote", { class: "texte-envoye" }, v.relance.texte) : null);
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
    const motif = el("textarea", {
      id: "motif", name: "motif", rows: "3", minlength: "1", maxlength: "500", required: true,
      oninput: (e) => { v.motif = e.currentTarget.value; },
    });
    motif.value = v.motif; // gardé entre deux rendus et au changement de sous-onglet
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

  function ficheSouscripteur() {
    const f = v.fiche;
    if (!f) return null;
    return el("section", { class: "fiche ne-pas-imprimer", "aria-labelledby": "titre-fiche" },
      el("h2", { id: "titre-fiche" }, picto(PICTOS.souscripteur), "Souscripteur"),
      el("dl", {},
        el("dt", {}, "Identité"), el("dd", {}, `${f.civilite} ${f.prenom} ${f.nom}`.trim()),
        el("dt", {}, "Adresse postale"), el("dd", {}, `${f.adresse}, ${f.code_postal}`),
        el("dt", {}, "Mobile"), el("dd", {}, el("a", { href: `tel:${f.mobile}` }, f.mobile)),
        el("dt", {}, "E-mail"), el("dd", {}, el("a", { href: `mailto:${f.email}` }, f.email)),
        f.vehicule && [el("dt", {}, "Véhicule"), el("dd", {}, vehicule(f.vehicule))]));
  }

  // Contrat imprimé sur le modèle d'Acerola (27/10) : conditions particulières numérotées, notice RGPD, puis
  // conditions générales (notice du contrat type) et références de la décision.
  function contratGenere() {
    const c = v.contrat;
    const s = c.souscripteur;
    const auto = c.vehicule;
    const jour = (d) => d.split("-").reverse().join("/"); // AAAA-MM-JJ → JJ/MM/AAAA, sans décalage de fuseau
    const euros = (x) => Number(x).toLocaleString("fr-FR", { style: "currency", currency: "EUR" });
    const cg = v.conditions;
    const ligne = (titre, valeur) => [el("dt", {}, titre), el("dd", {}, valeur)];
    return el("article", { class: "contrat-imprimable", "aria-labelledby": "titre-contrat" },
      el("h2", { id: "titre-contrat" }, "Contrat d'assurance automobile — conditions particulières"),
      el("p", { class: "discret" }, "AgentInsurFlow — document fictif généré pour le projet de certification."),
      el("dl", {},
        ligne("N° de contrat", c.numero_contrat),
        ligne("Date d'effet", jour(c.date_effet)),
        ligne("Date d'échéance", `${jour(dateEcheance(c.date_effet))} (reconduction tacite)`)),
      el("h3", {}, "1. Souscripteur et conducteur principal"),
      el("dl", {},
        ligne("Nom et prénom", `${s.nom.toUpperCase()} ${s.prenom}`),
        ligne("Date de naissance", jour(s.date_naissance)),
        ligne("Adresse postale", `${s.adresse}, ${s.code_postal}`),
        ligne("Téléphone", s.telephone),
        ligne("Adresse e-mail", s.email),
        ligne("N° de permis de conduire", `${s.permis_numero} (délivré le ${jour(s.permis_date_obtention)}, ${s.permis_pays})`),
        ligne("Coefficient bonus-malus (CRM)", c.crm_bonus_malus.toLocaleString("fr-FR", { minimumFractionDigits: 2 }))),
      el("h3", {}, "2. Véhicule assuré"),
      auto
        ? el("dl", {},
          ligne("Marque / modèle", `${auto.marque} ${auto.modele} ${auto.version}, ${auto.puissance_fiscale_cv} CV`),
          ligne("Immatriculation", auto.immatriculation),
          ligne("N° de série (VIN)", auto.vin),
          ligne("1re mise en circulation", jour(auto.date_mise_circulation)),
          ligne("Usage déclaré", USAGES[auto.type_usage] ?? auto.type_usage),
          ligne("Stationnement habituel", `${STATIONNEMENTS[auto.mode_stationnement] ?? auto.mode_stationnement} (${auto.code_postal_stationnement})`))
        : el("p", {}, "Véhicule non renseigné."),
      el("h3", {}, "3. Garanties et franchises"),
      el("p", {}, `Formule souscrite : ${FORMULES[c.formule] ?? c.formule} (contrat type ${c.contrat_type})`),
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Garantie"), el("th", { scope: "col" }, "Statut"),
          el("th", { scope: "col" }, "Franchise"))),
        el("tbody", {}, (c.garanties ?? []).map((g) => el("tr", {},
          el("td", {}, LIBELLES_GARANTIES[g.type] ?? g.type), el("td", {}, "Incluse"),
          el("td", {}, g.franchise === null ? "sans objet" : euros(g.franchise)))))),
      el("h3", {}, "4. Cotisation et modalités de paiement"),
      el("dl", {},
        ligne("Prime totale TTC", `${euros(c.prime_ttc_annuelle)} par an`),
        ligne("Mode de règlement", `Prélèvement automatique mensuel (${euros(c.prime_mensuelle)} par mois)`)),
      el("h3", {}, "5. Information RGPD et protection des données personnelles"),
      el("p", { class: "discret" }, "Notice synthétique (articles 13 et 14 du RGPD)."),
      el("ol", {},
        el("li", {}, "Responsable de traitement : AgentInsurFlow (assureur fictif du projet de certification)."),
        el("li", {}, "Finalités : souscription et gestion du contrat, tarification du risque, prévention de la fraude."),
        el("li", {}, "Base légale : exécution du contrat et mesures précontractuelles (article 6.1.b du RGPD)."),
        el("li", {}, "Décision : l'analyse automatisée porte sur un dossier minimisé (sans nom, adresse ni coordonnées) ; "
          + "la décision est toujours validée par un gestionnaire (article 22 du RGPD)."),
        el("li", {}, "Destinataires : le gestionnaire du contrat et les services internes de l'assureur ; l'hébergeur cloud "
          + "en tant que sous-traitant."),
        el("li", {}, "Durée de conservation : la durée de la relation contractuelle, puis l'archivage pendant les délais de "
          + "prescription applicables."),
        el("li", {}, "Vos droits : accès, rectification, effacement, limitation et opposition, auprès du délégué à la "
          + "protection des données (dpo@agentinsurflow.invalid) ; réclamation possible auprès de la CNIL.")),
      el("h3", {}, "Conditions générales"),
      cg
        ? [el("p", {}, cg.titre), ...cg.sections.flatMap((sec) => [
          sec.titre && el("h4", {}, sec.titre),
          ...sec.lignes.filter((l) => !l.puce).map((l) => el("p", {}, l.texte)),
          sec.lignes.some((l) => l.puce) && el("ul", {}, sec.lignes.filter((l) => l.puce).map((l) => el("li", {}, l.texte)))])]
        : el("p", {}, `Notice du contrat type « ${c.contrat_type} », consultable au corpus.`),
      el("h3", {}, "Références de la décision"),
      el("dl", { class: "discret" },
        ligne("Barème / formule", `${c.version_bareme} / ${c.version_formule}`),
        ...liste("Motifs", c.motifs),
        ...liste("Citations", c.citations)),
      el("p", {}, `Fait le ${new Date(c.valide_le).toLocaleDateString("fr-FR")}, contrat validé par le gestionnaire.`),
      el("p", {}, "Pour l'assureur (AgentInsurFlow) et le souscripteur."),
      el("p", { class: "signature" }, "Signature du souscripteur :"),
      el("button", { type: "button", class: "ne-pas-imprimer", onclick: () => window.print() }, picto(PICTOS.imprimer), "Imprimer"));
  }

  function sousOnglets() {
    const nb = manquantes().length;
    const panneaux = { detail: panneauDetail, pieces: panneauPieces, contrat: panneauContrat };
    const onglets = SOUS_ONGLETS.map(([cle, titre, icone]) =>
      el("button", {
        type: "button", role: "tab", id: `sous-${cle}`, "aria-controls": "sous-panneau",
        "aria-selected": String(v.sousOnglet === cle), tabindex: v.sousOnglet === cle ? "0" : "-1",
        onclick: () => {
          v.sousOnglet = cle;
          rendre();
          document.getElementById(`sous-${cle}`)?.focus();
        },
      }, picto(PICTOS[icone]), titre, cle === "pieces" && nb ? el("span", { class: "pastille", "aria-label": `${nb} manquante(s)` }, String(nb)) : null));
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
    // le rendu toutes les secondes ne doit voler ni le focus clavier ni la position du curseur dans un champ
    const actif = document.activeElement;
    const focus = actif?.id;
    const curseur = actif?.tagName === "TEXTAREA" ? [actif.selectionStart, actif.selectionEnd] : null;
    remplir(zone,
      el("p", { class: "ne-pas-imprimer" }, el("a", { href: "#/dossiers" }, "← Mes dossiers")),
      el("h1", {}, picto(PICTOS.dossier), `Dossier ${numero}`),
      el("p", { class: "discret" }, s ? `Statut : ${s} · tentative ${v.etat.tentative}` : "Jamais évalué"),
      ficheSouscripteur(),
      barreActions(),
      v.message,
      rendreFrise(),
      sousOnglets());
    const cible = focus ? document.getElementById(focus) : null;
    cible?.focus();
    if (curseur && cible?.tagName === "TEXTAREA") cible.setSelectionRange(...curseur);
  }

  remplir(zone, el("h1", {}, `Dossier ${numero}`), el("p", { "aria-busy": "true" }, "Chargement…"));
  if ((await lireEtat()) !== 200) return remplir(zone, el("p", {}, el("a", { href: "#/dossiers" }, "← Mes dossiers")), v.message);
  await lireFiche();
  if (statut() === "ACCEPTE") await lireContrat();
  if (statut() === "ACCEPTE" || statut() === "EN_ANALYSE") v.sousOnglet = "contrat";
  rendre();
  if (statut() === "EN_COURS") suivre(); // page rechargée pendant une évaluation
}

const FORMULES = { tiers: "Tiers", tiers_etendu: "Tiers étendu", tous_risques: "Tous risques" };
const USAGES = { prive: "Déplacements privés et trajets domicile-travail", professionnel: "Usage professionnel" };
const STATIONNEMENTS = { garage: "Garage fermé ou box", parking: "Parking", rue: "Voie publique" };

function vehicule(auto) {
  return `${auto.marque} ${auto.modele}, ${auto.immatriculation}, ${auto.puissance_fiscale_cv} CV, usage ${auto.type_usage}`;
}
