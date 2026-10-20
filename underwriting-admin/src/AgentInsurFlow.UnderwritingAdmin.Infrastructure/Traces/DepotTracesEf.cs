using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.EntityFrameworkCore;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Traces;

/// <summary>Le référentiel des traces : écrit avec <c>traces_writer</c> (INSERT seul), relit avec <c>traces_reader</c> (SELECT seul).</summary>
public sealed class DepotTracesEf(ConnexionsTraces connexions) : IDepotTraces
{
    public async Task<int> Inserer(IReadOnlyList<Span> spans, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(spans);
        await using var db = TracesDbContextFactory.Creer(connexions.Writer);
        await using var transaction = await db.Database.BeginTransactionAsync(ct);
        var inseres = 0;
        foreach (var s in spans)
        {
            // Tout est paramétré ; les ::jsonb viennent du texte reçu, jamais concaténé dans la requête.
            inseres += await db.Database.ExecuteSqlInterpolatedAsync($"""
                INSERT INTO span (trace_id, span_id, parent_span_id, trace_state, name, kind,
                    start_time_unix_nano, end_time_unix_nano, status_code, status_message, service_name,
                    resource_attributes, attributes, scope_name, scope_version, events, links, recu_le)
                VALUES ({s.TraceId}, {s.SpanId}, {s.ParentSpanId}, {s.TraceState}, {s.Name}, {(short)s.Kind},
                    {s.StartTimeUnixNano}, {s.EndTimeUnixNano}, {(short)s.StatusCode}, {s.StatusMessage}, {s.ServiceName},
                    {s.ResourceAttributes}::jsonb, {s.Attributes}::jsonb, {s.ScopeName}, {s.ScopeVersion},
                    {s.Events}::jsonb, {s.Links}::jsonb, {s.RecuLe})
                ON CONFLICT DO NOTHING
                """, ct);
        }
        await transaction.CommitAsync(ct);
        return inseres;
    }

    public async Task<IReadOnlyList<Span>> Lire(string traceId, CancellationToken ct)
    {
        await using var db = TracesDbContextFactory.Creer(connexions.Reader);
        var lignes = await db.Spans.AsNoTracking()
            .Where(x => x.TraceId == traceId)
            .OrderBy(x => x.StartTimeUnixNano).ThenBy(x => x.SpanId)
            .ToListAsync(ct);
        return lignes.ConvertAll(x => new Span(
            x.TraceId, x.SpanId, x.ParentSpanId, x.TraceState, x.Name, x.Kind, x.StartTimeUnixNano, x.EndTimeUnixNano,
            x.StatusCode, x.StatusMessage, x.ServiceName, x.ResourceAttributes, x.Attributes, x.ScopeName, x.ScopeVersion,
            x.Events, x.Links, x.RecuLe));
    }
}
