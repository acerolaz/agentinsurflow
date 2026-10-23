using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Écrase les observations du gestionnaire après contrôle du statut et de la longueur.</summary>
public sealed class EnregistrerObservations(IDepotEcritures depot)
{
    public async Task<ResultatEcriture> Executer(string gestionnaireId, string numeroContrat, string observations,
        CancellationToken ct)
    {
        if (await depot.StatutContrat(gestionnaireId, numeroContrat, ct) is not { } statut) return new(false, null);
        var refus = ReglesObservations.Refus(statut, observations);
        if (refus is not null) return new(false, refus);
        return new(await depot.EnregistrerObservations(gestionnaireId, numeroContrat, observations, ct), null);
    }
}
