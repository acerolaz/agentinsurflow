// Espace gestionnaire : routeur sur le fragment d'URL, en-tête à onglets, thème, portefeuille et tchat.
import { appeler } from "./api.js";
import { compteCourant, connecter, deconnecter, initialiser } from "./auth.js";
import { el, erreur, remplir } from "./dom.js";
import { routeDepuisHash, themeInitial } from "./logique.js";

const racine = document.getElementById("app");
const ONGLETS = [
  { vue: "dossiers", hash: "#/dossiers", titre: "Mes dossiers" },
  { vue: "tchat", hash: "#/tchat", titre: "Tchat corpus" },
];

// --- thème ---------------------------------------------------------------------------------------
function lireTheme() {
  try {
    return localStorage.getItem("theme");
  } catch {
    return null; // stockage bloqué : la préférence système suffit
  }
}

function appliquerTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("theme", theme);
  } catch {
    /* rien à garder */
  }
}

appliquerTheme(themeInitial(lireTheme(), matchMedia("(prefers-color-scheme: dark)").matches));

function boutonTheme() {
  const sombre = document.documentElement.dataset.theme === "sombre";
  return el("button", {
    type: "button", class: "secondaire", "aria-pressed": String(sombre),
    onclick: (e) => {
      const suivant = document.documentElement.dataset.theme === "sombre" ? "clair" : "sombre";
      appliquerTheme(suivant);
      e.currentTarget.setAttribute("aria-pressed", String(suivant === "sombre"));
    },
  }, "Thème sombre");
}

// --- connexion -----------------------------------------------------------------------------------
function vueConnexion() {
  const carte = (lettre) =>
    el("label", { class: "carte-compte" },
      el("input", { type: "radio", name: "compte", value: lettre, checked: lettre === "A" }),
      el("span", { class: "titre-carte" }, `Gestionnaire ${lettre}`),
      el("span", { class: "discret" }, lettre === "A" ? "Portefeuille A" : "Portefeuille B"));
  const formulaire = el("form", {
    class: "connexion",
    onsubmit: (e) => {
      e.preventDefault();
      connecter(new FormData(e.currentTarget).get("compte"));
    },
  },
  el("fieldset", {}, el("legend", {}, "Choisissez votre compte"), carte("A"), carte("B")),
  el("p", { class: "discret" }, "Le choix préremplit l'identifiant ; votre identité est vérifiée par Microsoft Entra."),
  el("button", { type: "submit" }, "Se connecter avec Microsoft"));
  remplir(racine, el("main", { id: "vue" }, el("h1", {}, "Espace gestionnaire"), formulaire, boutonTheme()));
}

// --- en-tête à onglets ---------------------------------------------------------------------------
function entete(vueActive) {
  const onglets = ONGLETS.map((o) =>
    el("a", {
      role: "tab", href: o.hash, id: `onglet-${o.vue}`, "aria-controls": "vue",
      "aria-selected": String(o.vue === vueActive), tabindex: o.vue === vueActive ? "0" : "-1",
    }, o.titre));
  const liste = el("nav", {
    role: "tablist", "aria-label": "Sections",
    onkeydown: (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const i = onglets.indexOf(document.activeElement);
      if (i < 0) return;
      const suivant = onglets[(i + (e.key === "ArrowRight" ? 1 : onglets.length - 1)) % onglets.length];
      suivant.focus();
      location.hash = suivant.getAttribute("href");
    },
  }, onglets);
  const compte = compteCourant();
  return el("header", { class: "entete" },
    el("span", { class: "marque" }, "AgentInsurFlow"),
    liste,
    el("span", { class: "discret" }, compte?.nom ?? ""),
    boutonTheme(),
    el("button", { type: "button", class: "secondaire", onclick: () => deconnecter() }, "Déconnexion"));
}

// --- portefeuille --------------------------------------------------------------------------------
async function vueDossiers(zone) {
  remplir(zone, el("h1", {}, "Mes dossiers"), el("p", { "aria-busy": "true" }, "Chargement…"));
  const r = await appeler("GET", "/api/contrats", { portee: "underwriting" });
  if (r.statut !== 200) return remplir(zone, el("h1", {}, "Mes dossiers"), erreur(r));
  const lignes = r.json.map((c) =>
    el("tr", {},
      el("th", { scope: "row" }, el("a", { href: `#/dossiers/${encodeURIComponent(c.numero_contrat)}` }, c.numero_contrat)),
      el("td", {}, c.formule),
      el("td", {}, `${c.tranche_age} ans, dép. ${c.departement}`),
      el("td", {}, c.date_effet),
      el("td", {}, new Date(c.mis_a_jour).toLocaleString("fr-FR"))));
  remplir(zone, el("h1", {}, "Mes dossiers"),
    lignes.length === 0
      ? el("p", {}, "Aucun dossier dans votre portefeuille.")
      : el("table", {},
        el("caption", { class: "discret" }, "Ouvrez un dossier avec Entrée sur son numéro."),
        el("thead", {}, el("tr", {}, ["Numéro", "Formule", "Profil", "Date d'effet", "Mis à jour"].map((t) => el("th", { scope: "col" }, t)))),
        el("tbody", {}, lignes)));
}

// --- tchat ---------------------------------------------------------------------------------------
const fil = el("ol", { class: "fil", "aria-live": "polite" });

function source(c) {
  const libelle = [c.collection, c.article].filter(Boolean).join(" — ") || c.table || "Source";
  const lien = typeof c.url_source === "string" && c.url_source.startsWith("https://")
    ? el("a", { href: c.url_source, target: "_blank", rel: "noopener noreferrer" }, libelle)
    : libelle;
  return el("li", {}, lien);
}

function vueTchat(zone) {
  const champ = el("textarea", { id: "question", name: "texte", rows: "3", maxlength: "2000", required: true });
  const formulaire = el("form", {
    class: "tchat",
    onsubmit: async (e) => {
      e.preventDefault();
      const texte = champ.value.trim();
      if (!texte) return;
      const bouton = e.currentTarget.querySelector("button");
      bouton.disabled = true;
      fil.append(el("li", { class: "question" }, texte));
      const r = await appeler("POST", "/api/reponses", { portee: "rag", corps: { texte } });
      bouton.disabled = false;
      if (r.statut !== 200) {
        fil.append(el("li", { class: "reponse" }, erreur(r)));
        return;
      }
      champ.value = "";
      const sources = r.json.citations ?? [];
      fil.append(el("li", { class: "reponse" },
        el("p", {}, r.json.texte),
        sources.length ? el("ul", { class: "sources", "aria-label": "Sources" }, sources.map(source)) : null));
    },
  },
  el("label", { for: "question" }, "Votre question sur le corpus"),
  champ,
  el("button", { type: "submit" }, "Envoyer"));
  remplir(zone, el("h1", {}, "Tchat corpus"), fil, formulaire);
  champ.focus();
}

// --- routeur -------------------------------------------------------------------------------------
async function afficher() {
  if (!compteCourant()) return vueConnexion();
  const route = routeDepuisHash(location.hash);
  const actif = route.vue === "tchat" ? "tchat" : "dossiers";
  const zone = el("main", { id: "vue", role: "tabpanel", "aria-labelledby": `onglet-${actif}` });
  remplir(racine, entete(actif), zone);
  if (route.vue === "tchat") return vueTchat(zone);
  if (route.vue === "dossier") {
    const { afficherDossier } = await import("./dossier.js");
    return afficherDossier(zone, route.numero);
  }
  return vueDossiers(zone);
}

window.addEventListener("hashchange", afficher);
initialiser().then(afficher, () => remplir(racine, el("p", { class: "erreur", role: "alert" }, "Connexion indisponible")));
