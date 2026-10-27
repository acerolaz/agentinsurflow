using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>
/// Confie l'état du dossier à la mémoire long terme (D100) après contrôle de la liste blanche des sections. Un dossier figé
/// garde son état : le cluster écrit l'état avant le statut, donc une décision en cours n'est jamais bloquée.
/// </summary>
public sealed class EnregistrerEtat(IDepotEcritures depot)
{
    public async Task<ResultatEcriture> Executer(string gestionnaireId, string numeroContrat, EtatEntrant etat, CancellationToken ct)
    {
        if (await depot.StatutContrat(gestionnaireId, numeroContrat, ct) is not { } statut) return new(false, null);
        if (ReglesStatut.Fige(statut)) return new(false, "STATUT_FIGE");
        var refus = ReglesEtat.Refus(etat);
        if (refus is not null) return new(false, refus);
        return new(await depot.EnregistrerEtat(gestionnaireId, numeroContrat, etat, ct), null);
    }
}
