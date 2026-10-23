using System.Security.Claims;
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
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404);

        contrats.MapPut("/{numero_contrat}/statut", async (ClaimsPrincipal utilisateur, ChangerStatut cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat, StatutCorps corps) =>
            ContratsEndpoints.Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                : Reponse(await cas.Executer(oid, numeroContrat, new ChangementStatut(corps.Statut ?? "", corps.Validation), ct)))
            .WithName("ChangerStatut")
            .WithSummary("Change le statut ; ACCEPTE/REFUSE exigent une validation (VALIDEE ou CORRIGEE)")
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404);

        contrats.MapPut("/{numero_contrat}/observations", async (ClaimsPrincipal utilisateur, EnregistrerObservations cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat, ObservationsCorps corps) =>
            ContratsEndpoints.Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                : Reponse(await cas.Executer(oid, numeroContrat, corps.Observations ?? "", ct)))
            .WithName("EnregistrerObservations")
            .WithSummary("Écrase les observations du gestionnaire (2000 caractères au plus) tant que le statut n'est pas figé")
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409);
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

/// <summary>Corps de <c>PUT …/observations</c>.</summary>
internal sealed record ObservationsCorps(string? Observations);
