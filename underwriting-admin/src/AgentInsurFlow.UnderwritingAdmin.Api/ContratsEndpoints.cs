using System.Security.Claims;
using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.AspNetCore.Mvc;

namespace AgentInsurFlow.UnderwritingAdmin.Api;

/// <summary>Les contrats du gestionnaire connecté : <c>gestionnaire_id</c> = claim <c>oid</c> du jeton, jamais un paramètre.</summary>
internal static class ContratsEndpoints
{
    public static void MapContrats(this IEndpointRouteBuilder app)
    {
        var contrats = app.MapGroup("/api/contrats").RequireAuthorization("Gestionnaire").WithTags("Contrats");

        contrats.MapGet("/", async (ClaimsPrincipal utilisateur, ListerPortefeuille cas, CancellationToken ct,
                [FromQuery] int limit = 20, [FromQuery] int offset = 0) =>
            Oid(utilisateur) is { } oid
                ? Results.Ok(await cas.Executer(oid, limit, offset, ct))
                : Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE"))
            .WithName("ListerContrats")
            .WithSummary("Contrats du gestionnaire connecté (vue minimisée), limit borné à 100")
            .Produces<IReadOnlyList<VueContrat>>()
            .ProducesProblem(401).ProducesProblem(403);

        contrats.MapGet("/{numero_contrat}", async (ClaimsPrincipal utilisateur, ConsulterContrat cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat) =>
            Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                // Même réponse pour « inexistant » et « à un autre gestionnaire » (BOLA) : rien n'indique que le numéro existe.
                : await cas.Executer(oid, numeroContrat, ct) is { } vue
                    ? Results.Ok(vue)
                    : Problemes.Creer(404, "Contrat introuvable", "CONTRAT_INTROUVABLE"))
            .WithName("ConsulterContrat")
            .WithSummary("Un contrat du gestionnaire connecté (vue minimisée)")
            .Produces<VueContrat>()
            .ProducesProblem(401).ProducesProblem(403).ProducesProblem(404);
    }

    private static string? Oid(ClaimsPrincipal u) =>
        u.FindFirst("oid")?.Value is { Length: > 0 } v ? v : null;
}
