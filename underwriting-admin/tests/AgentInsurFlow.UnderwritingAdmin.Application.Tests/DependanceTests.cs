using AgentInsurFlow.UnderwritingAdmin.Application;

namespace AgentInsurFlow.UnderwritingAdmin.Application.Tests;

/// <summary>Règle de dépendance : Application ne connaît que Domain.</summary>
public sealed class DependanceTests
{
    [Fact]
    public void Application_ne_reference_ni_Infrastructure_ni_Api()
    {
        var references = typeof(ListerPortefeuille).Assembly.GetReferencedAssemblies().Select(a => a.Name!).ToList();

        Assert.DoesNotContain(references, n => n.Contains("Infrastructure", StringComparison.Ordinal));
        Assert.DoesNotContain(references, n => n.EndsWith(".Api", StringComparison.Ordinal));
        Assert.DoesNotContain(references, n => n.StartsWith("Microsoft.AspNetCore", StringComparison.Ordinal));
    }
}
