using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Domain.Tests;

/// <summary>Règle de dépendance (Clean Architecture), vérifiée par les références d'assembly.</summary>
public sealed class DependanceTests
{
    [Fact]
    public void Domain_ne_reference_aucun_assembly_externe()
    {
        var externes = typeof(VueContrat).Assembly.GetReferencedAssemblies()
            .Select(a => a.Name!)
            .Where(n => !n.StartsWith("System", StringComparison.Ordinal) && n is not ("netstandard" or "mscorlib"));

        Assert.Empty(externes);
    }
}
