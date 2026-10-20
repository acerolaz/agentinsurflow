namespace AgentInsurFlow.UnderwritingAdmin.Domain.Tests;

/// <summary>TU : règles pures sur les identifiants et le nom de service des spans.</summary>
public sealed class ReglesTracesTests
{
    [Fact]
    public void Hexa_en_minuscules_et_longueur_controlee()
    {
        Assert.Equal("0aff", ReglesTraces.Hexa([0x0a, 0xff], 2));
        Assert.Throws<FormatException>(() => ReglesTraces.Hexa([1], 2));
    }

    [Fact]
    public void Service_absent_ou_vide_donne_inconnu()
    {
        Assert.Equal("inconnu", ReglesTraces.NomDeService(null));
        Assert.Equal("inconnu", ReglesTraces.NomDeService("  "));
        Assert.Equal("rag", ReglesTraces.NomDeService("rag"));
    }

    [Fact]
    public void TraceId_valide_seulement_en_32_hexa()
    {
        Assert.True(ReglesTraces.EstTraceIdValide("0af7651916cd43dd8448eb211c80319c"));
        Assert.False(ReglesTraces.EstTraceIdValide("0af7651916cd43dd8448eb211c80319"));
        Assert.False(ReglesTraces.EstTraceIdValide("zaf7651916cd43dd8448eb211c80319c"));
        Assert.False(ReglesTraces.EstTraceIdValide(null));
    }
}
