namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Règles pures sur les identifiants et le nom de service des spans.</summary>
public static class ReglesTraces
{
    public const string ServiceInconnu = "inconnu";

    /// <summary>Octets → hexadécimal minuscule ; <see cref="FormatException"/> si la longueur n'est pas celle d'OTLP.</summary>
    public static string Hexa(ReadOnlySpan<byte> octets, int longueurAttendue) =>
        octets.Length == longueurAttendue
            ? Convert.ToHexStringLower(octets)
            : throw new FormatException($"identifiant de {octets.Length} octets, {longueurAttendue} attendus");

    /// <summary><c>service.name</c> absent ou vide : « inconnu ».</summary>
    public static string NomDeService(string? serviceName) =>
        string.IsNullOrWhiteSpace(serviceName) ? ServiceInconnu : serviceName;

    /// <summary>Un <c>trace_id</c> valide : 32 caractères hexadécimaux.</summary>
    public static bool EstTraceIdValide(string? valeur) =>
        valeur is { Length: 32 } && valeur.All(char.IsAsciiHexDigit);
}
