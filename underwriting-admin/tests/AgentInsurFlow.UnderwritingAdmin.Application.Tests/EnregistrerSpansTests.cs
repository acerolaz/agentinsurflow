using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application.Tests;

/// <summary>TU : cas d'usage <see cref="EnregistrerSpans"/>, avec un port <see cref="IDepotTraces"/> simulé.</summary>
public sealed class EnregistrerSpansTests
{
    private sealed class DepotSimule : IDepotTraces
    {
        private readonly HashSet<(string, string)> _connus = [];

        public Task<int> Inserer(IReadOnlyList<Span> spans, CancellationToken ct) =>
            Task.FromResult(spans.Count(s => _connus.Add((s.TraceId, s.SpanId))));

        public Task<IReadOnlyList<Span>> Lire(string traceId, CancellationToken ct) =>
            Task.FromResult<IReadOnlyList<Span>>([]);
    }

    private static Span UnSpan() => new(
        "0af7651916cd43dd8448eb211c80319c", "b7ad6b7169203331", null, "", "rag.recherche", 2, 1, 2, 0, "", "rag",
        "{}", "{}", "", "", "[]", "[]", DateTimeOffset.UnixEpoch);

    [Fact]
    public async Task EnregistrerSpans_rejeu_idempotent()
    {
        var cas = new EnregistrerSpans(new DepotSimule());
        IReadOnlyList<Span> spans = [UnSpan()];

        var premier = await cas.Executer(spans, TestContext.Current.CancellationToken);
        var rejeu = await cas.Executer(spans, TestContext.Current.CancellationToken);

        Assert.Equal(1, premier);
        Assert.Equal(0, rejeu);
        Assert.Equal(0, await cas.Executer([], TestContext.Current.CancellationToken));
    }
}
