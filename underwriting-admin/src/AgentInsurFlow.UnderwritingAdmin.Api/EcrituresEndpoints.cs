using System.Diagnostics;
using System.Security.Claims;
using System.Text.Json;
using System.Text.Json.Serialization;
using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.AspNetCore.Mvc;

namespace AgentInsurFlow.UnderwritingAdmin.Api;

/// <summary>Écritures d'un dossier : brouillon d'instruction et changement de statut, bornées au gestionnaire du jeton (<c>oid</c>).</summary>
internal static class EcrituresEndpoints
{
    public static void MapEcritures(this IEndpointRouteBuilder app)
    {
        var contrats = app.MapGroup("/api/contrats").RequireAuthorization("Gestionnaire").WithTags("Contrats");

        contrats.MapPut("/{numero_contrat}/brouillon", async (ClaimsPrincipal utilisateur, EnregistrerBrouillon cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat, BrouillonCorps corps) =>
            ContratsEndpoints.Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                : Reponse(await cas.Executer(oid, numeroContrat, corps.Fiche, corps.Prime, ct)))
            .WithName("EnregistrerBrouillon")
            .WithSummary("Enregistre (ou remplace) la fiche et la prime en brouillon, sans changer le statut")
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409);

        contrats.MapPut("/{numero_contrat}/statut", async (ClaimsPrincipal utilisateur, ChangerStatut cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat, StatutCorps corps) =>
            ContratsEndpoints.Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                : Reponse(await cas.Executer(oid, numeroContrat, new ChangementStatut(corps.Statut ?? "", corps.Validation), ct)))
            .WithName("ChangerStatut")
            .WithSummary("Change le statut ; ACCEPTE/REFUSE exigent une validation (VALIDEE ou CORRIGEE)")
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409);

        contrats.MapPut("/{numero_contrat}/observations", async (ClaimsPrincipal utilisateur, EnregistrerObservations cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat, ObservationsCorps corps) =>
            ContratsEndpoints.Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                : Reponse(await cas.Executer(oid, numeroContrat, corps.Observations ?? "", ct)))
            .WithName("EnregistrerObservations")
            .WithSummary("Écrase les observations du gestionnaire (2000 caractères au plus) tant que le statut n'est pas figé")
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409);

        contrats.MapPut("/{numero_contrat}/etat", async (ClaimsPrincipal utilisateur, EnregistrerEtat cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat, EtatCorps corps) =>
            ContratsEndpoints.Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                : Reponse(await cas.Executer(oid, numeroContrat, corps.Vers(), ct)))
            .WithName("EnregistrerEtat")
            .WithSummary("Mémoire long terme du dossier (D100), idempotente : sections connues seulement, aucune donnée identifiante")
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404);

        contrats.MapPost("/{numero_contrat}/relances", async (ClaimsPrincipal utilisateur, EnregistrerRelance cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat, RelanceCorps corps) =>
            ContratsEndpoints.Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                : Relance(await cas.Executer(oid, numeroContrat, corps.Texte ?? "", corps.Pieces ?? [], ct), corps.Pieces ?? []))
            .WithName("EnregistrerRelance")
            .WithSummary("Relance de pièces manquantes, enregistrée et tracée comme envoyée (aucun e-mail avant #123), 3 au plus")
            .Produces<RelanceReponse>(201)
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409);
    }

    // Le span porte le rang et les pièces, jamais le texte (il peut contenir des données personnelles).
    private static IResult Relance(ResultatRelance r, IReadOnlyList<string> pieces)
    {
        if (r.Rang is not { } rang)
            return r.CodeRefus switch
            {
                null => Problemes.Creer(404, "Contrat introuvable", "CONTRAT_INTROUVABLE"),
                ReglesRelance.Epuisees => Problemes.Creer(409, "Relances épuisées", ReglesRelance.Epuisees),
                ReglesRelance.Decide => Problemes.Creer(409, "Ce dossier a déjà reçu sa décision", ReglesRelance.Decide),
                ReglesRelance.Concurrente => Problemes.Creer(409, "Une autre relance vient d'être enregistrée", ReglesRelance.Concurrente),
                var code => Problemes.Creer(400, "Relance refusée", code),
            };
        Activity.Current?.SetTag("relance.rang", rang).SetTag("relance.max", ReglesRelance.Max)
            .SetTag("relance.pieces", string.Join(",", pieces));
        return Results.Json(new RelanceReponse(rang, ReglesRelance.Max), statusCode: 201);
    }

    // Même 404 pour « inexistant » et « à un autre gestionnaire » (BOLA).
    private static IResult Reponse(ResultatEcriture r) =>
        r is { Ecrit: true } ? Results.NoContent()
        : r.CodeRefus == "STATUT_FIGE" ? Problemes.Creer(409, "Statut figé", "STATUT_FIGE")
        : r.CodeRefus is { } code ? Problemes.Creer(400, "Écriture refusée", code)
        : Problemes.Creer(404, "Contrat introuvable", "CONTRAT_INTROUVABLE");
}

/// <summary>Corps de <c>PUT …/brouillon</c> ; la prime est facultative.</summary>
internal sealed record BrouillonCorps(FicheBrouillon Fiche, PrimeBrouillon? Prime);

/// <summary>Corps de <c>PUT …/statut</c> : le JSON dit <c>statut</c>, le domaine <c>StatutCible</c>.</summary>
internal sealed record StatutCorps(string? Statut, string? Validation);

/// <summary>Corps de <c>POST …/relances</c> : le texte modifié par le gestionnaire et les pièces réclamées.</summary>
internal sealed record RelanceCorps(string? Texte, List<string>? Pieces);

internal sealed record RelanceReponse(int Rang, int Max);

/// <summary>Corps de <c>PUT …/observations</c>.</summary>
internal sealed record ObservationsCorps(string? Observations);

/// <summary>Corps de <c>PUT …/etat</c> : l'état tel que le fusionne la Saga ; les contenus restent des documents JSON.</summary>
internal sealed record EtatCorps(
    [property: JsonPropertyName("statut_parcours")] string? StatutParcours,
    int Tentative,
    List<SectionCorps>? Sections,
    List<RapportCorps>? Rapports,
    List<TourCorps>? Tours)
{
    public EtatEntrant Vers() => new(StatutParcours ?? "", Tentative,
        [.. (Sections ?? []).Select(s => new SectionEntrante(s.Section ?? "", Json(s.Contenu)))],
        [.. (Rapports ?? []).Select(r => new RapportEntrant(r.Agent ?? "", Json(r.Rapport), r.Mode ?? "", r.Cause, r.VersionPrompt ?? "", r.TraceId ?? ""))],
        [.. (Tours ?? []).Select(t => new TourEntrant(t.Tour, t.OutilAppele ?? "", t.Precondition ?? "", t.Mode ?? ""))]);

    private static string Json(JsonElement? contenu) => contenu?.GetRawText() ?? "{}";
}

internal sealed record SectionCorps(string? Section, JsonElement? Contenu);

internal sealed record RapportCorps(string? Agent, JsonElement? Rapport, string? Mode, string? Cause,
    [property: JsonPropertyName("version_prompt")] string? VersionPrompt,
    [property: JsonPropertyName("trace_id")] string? TraceId);

internal sealed record TourCorps(int Tour,
    [property: JsonPropertyName("outil_appele")] string? OutilAppele, string? Precondition, string? Mode);
