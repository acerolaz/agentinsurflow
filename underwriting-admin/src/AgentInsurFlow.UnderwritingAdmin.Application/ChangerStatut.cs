using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Change le statut d'un dossier ; <see cref="ReglesStatut.Refus"/> passe avant tout appel au port.</summary>
public sealed class ChangerStatut(IDepotEcritures depot)
{
    public async Task<ResultatEcriture> Executer(string gestionnaireId, string numeroContrat,
        ChangementStatut changement, CancellationToken ct)
    {
        var refus = ReglesStatut.Refus(changement.StatutCible, changement.Validation);
        if (refus is not null) return new(false, refus);
        return new(await depot.ChangerStatut(gestionnaireId, numeroContrat, changement, gestionnaireId, ct), null);
    }
}
