using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using NpgsqlTypes;

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
        foreach (var lot in spans.Chunk(SpansParLot))
        {
            var (sql, parametres) = InsertionParLot(lot);
            inseres += await db.Database.ExecuteSqlRawAsync(sql, parametres, ct);
        }
        await transaction.CommitAsync(ct);
        return inseres;
    }

    // Un INSERT multi-lignes par lot : 18 paramètres par span, sous la limite de 65 535 de PostgreSQL.
    internal const int SpansParLot = 1000;

    // Tout est paramétré et typé (parent_span_id peut être NULL) ; le JSON reçu est casté en jsonb, jamais concaténé.
    internal static (string Sql, NpgsqlParameter[] Parametres) InsertionParLot(IReadOnlyList<Span> lot)
    {
        var parametres = new List<NpgsqlParameter>(lot.Count * 18);
        var lignes = new List<string>(lot.Count);
        string P(object? valeur, NpgsqlDbType type)
        {
            var nom = $"p{parametres.Count}";
            parametres.Add(new NpgsqlParameter(nom, type) { Value = valeur ?? DBNull.Value });
            return "@" + nom;
        }
        foreach (var s in lot)
        {
            lignes.Add($"({P(s.TraceId, NpgsqlDbType.Char)}, {P(s.SpanId, NpgsqlDbType.Char)}, "
                + $"{P(s.ParentSpanId, NpgsqlDbType.Char)}, {P(s.TraceState, NpgsqlDbType.Text)}, "
                + $"{P(s.Name, NpgsqlDbType.Text)}, {P((short)s.Kind, NpgsqlDbType.Smallint)}, "
                + $"{P(s.StartTimeUnixNano, NpgsqlDbType.Bigint)}, {P(s.EndTimeUnixNano, NpgsqlDbType.Bigint)}, "
                + $"{P((short)s.StatusCode, NpgsqlDbType.Smallint)}, {P(s.StatusMessage, NpgsqlDbType.Text)}, "
                + $"{P(s.ServiceName, NpgsqlDbType.Text)}, {P(s.ResourceAttributes, NpgsqlDbType.Jsonb)}, "
                + $"{P(s.Attributes, NpgsqlDbType.Jsonb)}, {P(s.ScopeName, NpgsqlDbType.Text)}, "
                + $"{P(s.ScopeVersion, NpgsqlDbType.Text)}, {P(s.Events, NpgsqlDbType.Jsonb)}, "
                + $"{P(s.Links, NpgsqlDbType.Jsonb)}, {P(s.RecuLe, NpgsqlDbType.TimestampTz)})");
        }
        var sql = $"""
            INSERT INTO span (trace_id, span_id, parent_span_id, trace_state, name, kind,
                start_time_unix_nano, end_time_unix_nano, status_code, status_message, service_name,
                resource_attributes, attributes, scope_name, scope_version, events, links, recu_le)
            VALUES {string.Join(",\n    ", lignes)}
            ON CONFLICT DO NOTHING
            """;
        return (sql, parametres.ToArray());
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
