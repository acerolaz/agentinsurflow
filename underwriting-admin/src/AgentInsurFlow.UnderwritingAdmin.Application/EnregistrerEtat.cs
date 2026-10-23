using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Confie l'état du dossier à la mémoire long terme (D100) après contrôle de la liste blanche des sections.</summary>
public sealed class EnregistrerEtat(IDepotEcritures depot)
{
    public async Task<ResultatEcriture> Executer(string gestionnaireId, string numeroContrat, EtatEntrant etat, CancellationToken ct)
    {
        if (await depot.StatutContrat(gestionnaireId, numeroContrat, ct) is null) return new(false, null);
        var refus = ReglesEtat.Refus(etat);
        if (refus is not null) return new(false, refus);
        return new(await depot.EnregistrerEtat(gestionnaireId, numeroContrat, etat, ct), null);
    }
}
