using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Fin de parcours (K8) : le gestionnaire classe le dossier sans suite après la dernière relance restée sans réponse.</summary>
public sealed class ClasserSansSuite(IDepotRelances depot)
{
    public async Task<ResultatEcriture> Executer(string gestionnaireId, string numeroContrat, CancellationToken ct)
    {
        if (await depot.Situation(gestionnaireId, numeroContrat, ct) is not { } situation) return new(false, null);
        if (ReglesRelance.RefusSansSuite(situation) is { } refus) return new(false, refus);
        return await depot.ClasserSansSuite(gestionnaireId, numeroContrat, ct)
            ? new(true, null)
            : new(false, ReglesRelance.Decide);
    }
}
