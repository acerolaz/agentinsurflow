// Espace gestionnaire : routeur sur le fragment d'URL, en-tête à onglets, thème, portefeuille et tchat.
import { appeler } from "./api.js";
import { compteCourant, connecter, deconnecter, initialiser } from "./auth.js";
import { el, erreur, picto, remplir } from "./dom.js";
import { PICTOS, routeDepuisHash, themeInitial } from "./logique.js";

const racine = document.getElementById("app");
const ONGLETS = [
  { vue: "dossiers", hash: "#/dossiers", titre: "Mes dossiers", picto: PICTOS.dossiers },
  { vue: "tchat", hash: "#/tchat", titre: "Tchat corpus", picto: PICTOS.tchat },
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
// Des liens de navigation (chacun atteignable par Tab, K6), pas un tablist : ils changent de page.
function entete(vueActive) {
  const liste = el("nav", { "aria-label": "Sections" }, ONGLETS.map((o) =>
    el("a", { href: o.hash, "aria-current": o.vue === vueActive ? "page" : null }, picto(o.picto), o.titre)));
  const compte = compteCourant();
  return el("header", { class: "entete" },
    el("span", { class: "marque" }, picto(PICTOS.marque), "AgentInsurFlow"),
    liste,
    el("span", { class: "discret" }, compte?.nom ?? ""),
    boutonTheme(),
    el("button", { type: "button", class: "secondaire", onclick: () => deconnecter() }, "Déconnexion"));
}

// --- portefeuille --------------------------------------------------------------------------------
async function vueDossiers(zone) {
  remplir(zone, el("h1", {}, "Mes dossiers"), el("p", { "aria-busy": "true" }, "Chargement…"));
  const r = await appeler("GET", "/api/contrats", { portee: "underwriting" });
  if (r.statut !== 200) return remplir(zone, el("h1", {}, picto(PICTOS.dossiers), "Mes dossiers"), erreur(r));
  const lignes = r.json.map((c) =>
    el("tr", {},
      el("th", { scope: "row" }, picto(PICTOS.dossier), el("a", { href: `#/dossiers/${encodeURIComponent(c.numero_contrat)}` }, c.numero_contrat)),
      el("td", {}, c.formule),
      el("td", {}, `${c.tranche_age} ans, dép. ${c.departement}`),
      el("td", {}, c.date_effet),
      el("td", {}, new Date(c.mis_a_jour).toLocaleString("fr-FR"))));
  remplir(zone, el("h1", {}, picto(PICTOS.dossiers), "Mes dossiers"),
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
  remplir(zone, el("h1", {}, picto(PICTOS.tchat), "Tchat corpus"), fil, formulaire);
  champ.focus();
}

// --- routeur -------------------------------------------------------------------------------------
async function afficher() {
  if (!compteCourant()) return vueConnexion();
  const route = routeDepuisHash(location.hash);
  const actif = route.vue === "tchat" ? "tchat" : "dossiers";
  const zone = el("main", { id: "vue" });
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
