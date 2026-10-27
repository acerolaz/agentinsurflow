using System.Security.Claims;
using System.Text.Json;
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

        contrats.MapGet("/{numero_contrat}/pieces", async (ClaimsPrincipal utilisateur, ListerPieces cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat) =>
            Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                // Même 404 pour « inexistant » et « à un autre gestionnaire » (BOLA).
                : await cas.Executer(oid, numeroContrat, ct) is { } pieces
                    ? Results.Ok(pieces)
                    : Problemes.Creer(404, "Contrat introuvable", "CONTRAT_INTROUVABLE"))
            .WithName("ListerPieces")
            .WithSummary("Pièces déclarées du contrat (type et date d'émission seulement)")
            .Produces<IReadOnlyList<PieceDeclaree>>()
            .ProducesProblem(401).ProducesProblem(403).ProducesProblem(404);

        contrats.MapGet("/{numero_contrat}/etat", async (ClaimsPrincipal utilisateur, LireEtat cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat) =>
            Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                // Même 404 pour « inexistant » et « à un autre gestionnaire » (BOLA).
                : await cas.Executer(oid, numeroContrat, ct) is { } etat
                    ? Results.Ok(EtatReponse.Depuis(etat))
                    : Problemes.Creer(404, "Contrat introuvable", "CONTRAT_INTROUVABLE"))
            .WithName("LireEtat")
            .WithSummary("Progression du dossier (tentative courante) : rapports des agents et sections lisibles, sans donnée identifiante")
            .Produces<EtatReponse>()
            .ProducesProblem(401).ProducesProblem(403).ProducesProblem(404);

        contrats.MapGet("/{numero_contrat}/contrat", async (ClaimsPrincipal utilisateur, LireContratGenere cas, CancellationToken ct,
                [FromRoute(Name = "numero_contrat")] string numeroContrat) =>
            Oid(utilisateur) is not { } oid
                ? Problemes.Creer(403, "Jeton sans identité de gestionnaire", "ACCES_REFUSE")
                : await cas.Executer(oid, numeroContrat, ct) switch
                {
                    ({ } contrat, _) => Results.Ok(contrat),
                    (null, true) => Problemes.Creer(409, "Contrat non accepté", "CONTRAT_NON_ACCEPTE"),
                    _ => Problemes.Creer(404, "Contrat introuvable", "CONTRAT_INTROUVABLE"),
                })
            .WithName("LireContratGenere")
            .WithSummary("Contrat généré après ACCEPTE (conditions particulières) : décision validée, prime, formule, souscripteur et véhicule ; ni e-mail ni téléphone")
            .Produces<ContratGenere>()
            .ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409);
    }

    internal static string? Oid(ClaimsPrincipal u) =>
        u.FindFirst("oid")?.Value is { Length: > 0 } v ? v : null;
}

/// <summary>Réponse de <c>GET …/etat</c> : les sections restent des documents JSON (écrits par la Saga).</summary>
internal sealed record EtatReponse(string? StatutParcours, int Tentative, int NbRelances,
    IReadOnlyList<RapportLu> Rapports, IReadOnlyDictionary<string, JsonElement> Sections)
{
    public static EtatReponse Depuis(EtatLu e) => new(e.StatutParcours, e.Tentative, e.NbRelances, e.Rapports,
        e.Sections.ToDictionary(s => s.Key, s =>
        {
            using var doc = JsonDocument.Parse(s.Value);
            return doc.RootElement.Clone();
        }));
}
