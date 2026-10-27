// Vue d'un dossier (#104) : complétée par la frise, la pause, la revue et le contrat.
import { el, remplir } from "./dom.js";

export function afficherDossier(zone, numero) {
  remplir(zone, el("p", {}, el("a", { href: "#/dossiers" }, "← Mes dossiers")), el("h1", {}, `Dossier ${numero}`));
}
