using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using AgentInsurFlow.UnderwritingAdmin.Infrastructure.Otlp;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Net.Http.Headers;

namespace AgentInsurFlow.UnderwritingAdmin.Api;

/// <summary>Référentiel SQL des traces : réception OTLP/HTTP protobuf et relecture d'une trace.</summary>
internal static class TracesEndpoints
{
    private const string Protobuf = "application/x-protobuf";

    public static void MapTraces(this IEndpointRouteBuilder app)
    {
        // Chemin imposé par le protocole OTLP. Pas de .Accepts() : le routage répondrait 415 avant l'autorisation, par la
        // politique de repli (401 pour une source locale sans jeton) ; le type est donc vérifié dans la route.
        app.MapPost("/v1/traces", async (HttpRequest requete, EnregistrerSpans cas, TimeProvider horloge, CancellationToken ct) =>
            {
                if (!MediaTypeHeaderValue.TryParse(requete.ContentType, out var type) || !type.MediaType.Equals(Protobuf, StringComparison.OrdinalIgnoreCase))
                {
                    return Problemes.Creer(415, "OTLP/HTTP : seul application/x-protobuf est accepté", "TYPE_NON_SUPPORTE");
                }
                using var corps = new MemoryStream();
                await requete.Body.CopyToAsync(corps, ct);
                IReadOnlyList<Span> spans;
                try
                {
                    spans = OtlpVersSpans.Convertir(corps.ToArray(), horloge.GetUtcNow());
                }
                catch (FormatException)
                {
                    return Problemes.Creer(400, "Requête OTLP illisible", "OTLP_INVALIDE");
                }
                await cas.Executer(spans, ct);
                return Results.Bytes([], Protobuf); // ExportTraceServiceResponse vide : tout est accepté
            })
            .RequireAuthorization("Otlp")
            .WithTags("Traces")
            .WithName("RecevoirTraces")
            .WithSummary("Reçoit des spans OTLP/HTTP (protobuf) ; sans jeton seulement depuis une source locale sans X-Forwarded-For")
            .Produces(200, contentType: Protobuf)
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(415);

        app.MapGet("/api/traces/{trace_id}", async (LireTrace cas, CancellationToken ct, [FromRoute(Name = "trace_id")] string traceId) =>
            {
                if (!ReglesTraces.EstTraceIdValide(traceId))
                {
                    return Problemes.Creer(400, "trace_id : 32 caractères hexadécimaux attendus", "TRACE_ID_INVALIDE");
                }
                var spans = await cas.Executer(traceId.ToLowerInvariant(), ct);
                return spans.Count == 0
                    ? Problemes.Creer(404, "Trace introuvable", "TRACE_INTROUVABLE")
                    : Results.Ok(spans.Select(SpanReponse.Depuis).ToList());
            })
            .RequireAuthorization("Gestionnaire")
            .WithTags("Traces")
            .WithName("LireTrace")
            .WithSummary("Les spans d'une trace, dans l'ordre de leur début")
            .Produces<IReadOnlyList<SpanReponse>>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404);
    }
}

/// <summary>Un span en réponse : attributs, événements et liens rendus en JSON (jamais en texte échappé).</summary>
internal sealed record SpanReponse(
    string TraceId, string SpanId, string? ParentSpanId, string TraceState, string Name, int Kind,
    long StartTimeUnixNano, long EndTimeUnixNano, double DureeMs, int StatusCode, string StatusMessage,
    string ServiceName, JsonElement ResourceAttributes, JsonElement Attributes, string ScopeName, string ScopeVersion,
    JsonElement Events, JsonElement Links, DateTimeOffset RecuLe)
{
    public static SpanReponse Depuis(Span s) => new(
        s.TraceId, s.SpanId, s.ParentSpanId, s.TraceState, s.Name, s.Kind, s.StartTimeUnixNano, s.EndTimeUnixNano,
        s.DureeMs, s.StatusCode, s.StatusMessage, s.ServiceName, Json(s.ResourceAttributes), Json(s.Attributes),
        s.ScopeName, s.ScopeVersion, Json(s.Events), Json(s.Links), s.RecuLe);

    private static JsonElement Json(string texte)
    {
        using var doc = JsonDocument.Parse(texte);
        return doc.RootElement.Clone();
    }
}
