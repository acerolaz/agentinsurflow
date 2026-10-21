namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Département tiré du code postal, à la place de l'adresse. Même règle que la vue SQL.</summary>
public static class Departement
{
    /// <summary>Outre-mer (97x, 98x) : trois caractères au plus, comme <c>left(…, 3)</c> ; Corse (« 2A004 ») et métropole : deux.</summary>
    public static string Depuis(string codePostal)
    {
        ArgumentNullException.ThrowIfNull(codePostal);
        if (codePostal.Length < 2)
        {
            throw new ArgumentException("Code postal trop court", nameof(codePostal));
        }
        var outreMer = codePostal.StartsWith("97", StringComparison.Ordinal) || codePostal.StartsWith("98", StringComparison.Ordinal);
        return codePostal[..Math.Min(outreMer ? 3 : 2, codePostal.Length)];
    }
}
