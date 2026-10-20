using AgentInsurFlow.UnderwritingAdmin.Infrastructure;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Tests;

/// <summary>Règle de dépendance : Infrastructure dépend de Application/Domain, jamais de Api.</summary>
public sealed class DependanceTests
{
    [Fact]
    public void Infrastructure_ne_reference_pas_Api()
    {
        var references = typeof(Marqueur).Assembly.GetReferencedAssemblies().Select(a => a.Name!).ToList();

        Assert.DoesNotContain(references, n => n.EndsWith(".Api", StringComparison.Ordinal));
    }
}
