namespace AgentInsurFlow.UnderwritingAdmin.Domain;

/// <summary>Tranche d'âge exposée à la place de la date de naissance. Même règle que la vue SQL.</summary>
public static class TrancheAge
{
    public static string Depuis(int age) => age switch
    {
        < 25 => "<25",
        < 40 => "25-39",
        < 60 => "40-59",
        _ => "60+",
    };
}
