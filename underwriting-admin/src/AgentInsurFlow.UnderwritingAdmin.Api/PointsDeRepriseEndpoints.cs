using AgentInsurFlow.UnderwritingAdmin.Infrastructure.PointsDeReprise;
using Microsoft.AspNetCore.Mvc;

namespace AgentInsurFlow.UnderwritingAdmin.Api;

/// <summary>
/// Points de reprise LangGraph du cluster (D106) : stockage opaque, réservé au rôle <c>PointsDeReprise</c>.
/// Le corps n'est jamais tracé ni journalisé ; le fil (<c>thread_id</c>) est un numéro de contrat, masqué dans les spans.
/// </summary>
internal static class PointsDeRepriseEndpoints
{
    public static void MapPointsDeReprise(this IEndpointRouteBuilder app)
    {
        var points = app.MapGroup("/api/points-de-reprise").RequireAuthorization("PointsDeReprise").WithTags("PointsDeReprise");

        points.MapGet("/{thread_id}", async (IDepotPointsDeReprise depot, CancellationToken ct,
                [FromRoute(Name = "thread_id")] string threadId, string? ns, string? id) =>
            await depot.LireAsync(threadId, ns ?? "", id, ct) is { } point
                ? Results.Json(PointReponse.De(point))
                : Problemes.Creer(404, "Point de reprise introuvable", "POINT_DE_REPRISE_INTROUVABLE"))
            .WithName("LirePointDeReprise")
            .WithSummary("Le point demandé (id), ou le dernier du fil, avec ses écritures en attente")
            .Produces<PointReponse>()
            .ProducesProblem(401).ProducesProblem(403).ProducesProblem(404);

        points.MapGet("/{thread_id}/liste", async (IDepotPointsDeReprise depot, CancellationToken ct,
                [FromRoute(Name = "thread_id")] string threadId, string? ns, string? avant, int? limite) =>
            limite is < 1
                ? Problemes.Creer(400, "limite doit être positive", "CORPS_INVALIDE")
                : Results.Json(new ListeReponse([.. (await depot.ListerAsync(threadId, ns, avant, limite, ct)).Select(PointReponse.De)])))
            .WithName("ListerPointsDeReprise")
            .WithSummary("Les points du fil, checkpoint_id décroissant")
            .Produces<ListeReponse>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403);

        points.MapPut("/{thread_id}", async (IDepotPointsDeReprise depot, CancellationToken ct,
                [FromRoute(Name = "thread_id")] string threadId, PointCorps corps) =>
            {
                if (corps.Vers(threadId) is not { } point) return Corps400();
                await depot.EcrireAsync(point, ct);
                return Results.NoContent();
            })
            .WithName("EcrirePointDeReprise")
            .WithSummary("Upsert d'un point (dernier écrit gagnant)")
            .Produces(204)
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403);

        points.MapPut("/{thread_id}/ecritures", async (IDepotPointsDeReprise depot, CancellationToken ct,
                [FromRoute(Name = "thread_id")] string threadId, EcrituresCorps corps) =>
            {
                if (corps.CheckpointId is not { Length: > 0 } || corps.TaskId is null || corps.Ecritures is null
                    || corps.Ecritures.Any(e => e.Canal is null || e.Type is null || e.Valeur is null))
                {
                    return Corps400();
                }
                var taskPath = corps.TaskPath ?? "";
                await depot.EcrireEcrituresAsync(threadId, corps.Ns ?? "", corps.CheckpointId, corps.TaskId, taskPath,
                    [.. corps.Ecritures.Select(e => new EcritureEnAttente(corps.TaskId, e.Idx, e.Canal!, e.Type!, e.Valeur!, taskPath))], ct);
                return Results.NoContent();
            })
            .WithName("EcrireEcrituresDePointDeReprise")
            .WithSummary("Écritures en attente d'une tâche (idx < 0 : remplacées ; sinon écrites une seule fois)")
            .Produces(204)
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403);

        points.MapDelete("/{thread_id}", async (IDepotPointsDeReprise depot, CancellationToken ct,
                [FromRoute(Name = "thread_id")] string threadId) =>
            {
                await depot.SupprimerFilAsync(threadId, ct);
                return Results.NoContent();
            })
            .WithName("SupprimerFilDePointsDeReprise")
            .WithSummary("Supprime tous les points et écritures du fil")
            .Produces(204)
            .ProducesProblem(401).ProducesProblem(403);
    }

    private static IResult Corps400() => Problemes.Creer(400, "Corps invalide", "CORPS_INVALIDE");
}

/// <summary>Corps de <c>PUT /{thread_id}</c> : octets en base64, jamais interprétés.</summary>
internal sealed record PointCorps(
    string? Ns, string? CheckpointId, string? ParentId, string? Type, byte[]? Checkpoint, string? TypeMetadata, byte[]? Metadata)
{
    public PointDeReprise? Vers(string threadId) =>
        CheckpointId is { Length: > 0 } && Type is not null && Checkpoint is not null && TypeMetadata is not null && Metadata is not null
            ? new PointDeReprise(threadId, Ns ?? "", CheckpointId, ParentId, Type, Checkpoint, TypeMetadata, Metadata, [])
            : null;
}

internal sealed record EcrituresCorps(string? Ns, string? CheckpointId, string? TaskId, string? TaskPath, List<EcritureCorps>? Ecritures);

internal sealed record EcritureCorps(int Idx, string? Canal, string? Type, byte[]? Valeur);

internal sealed record EcritureReponse(string TaskId, int Idx, string Canal, string Type, byte[] Valeur, string TaskPath);

internal sealed record PointReponse(
    string Ns, string CheckpointId, string? ParentId, string Type, byte[] Checkpoint, string TypeMetadata, byte[] Metadata,
    List<EcritureReponse> Ecritures)
{
    public static PointReponse De(PointDeReprise p) => new(p.Ns, p.CheckpointId, p.ParentId, p.Type, p.Checkpoint, p.TypeMetadata, p.Metadata,
        [.. p.Ecritures.Select(e => new EcritureReponse(e.TaskId, e.Idx, e.Canal, e.Type, e.Valeur, e.TaskPath))]);
}

internal sealed record ListeReponse(List<PointReponse> Points);
