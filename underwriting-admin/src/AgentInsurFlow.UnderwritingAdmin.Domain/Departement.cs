namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Département tiré du code postal, à la place de l'adresse. Même règle que la vue SQL.</summary>
public static class Departement
{
    /// <summary>
    /// Outre-mer (97x, 98x) : trois caractères au plus, comme <c>left(…, 3)</c> ; métropole : deux. Corse : code postal
    /// réel 20000-20199 → 2A, 20200 et au-delà → 2B ; la forme « 2A004 » donne ses deux premiers caractères.
    /// </summary>
    public static string Depuis(string codePostal)
    {
        ArgumentNullException.ThrowIfNull(codePostal);
        if (codePostal.Length < 2)
        {
            throw new ArgumentException("Code postal trop court", nameof(codePostal));
        }
        if (codePostal.Length == 5 && codePostal.StartsWith("20", StringComparison.Ordinal) && codePostal.All(char.IsAsciiDigit))
        {
            return string.CompareOrdinal(codePostal, "20200") < 0 ? "2A" : "2B";
        }
        var outreMer = codePostal.StartsWith("97", StringComparison.Ordinal) || codePostal.StartsWith("98", StringComparison.Ordinal);
        return codePostal[..Math.Min(outreMer ? 3 : 2, codePostal.Length)];
    }
}
