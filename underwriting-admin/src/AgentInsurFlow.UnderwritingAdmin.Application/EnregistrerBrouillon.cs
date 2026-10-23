using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Enregistre la fiche (et la prime) en brouillon après contrôle de la décision et de la périodicité.</summary>
public sealed class EnregistrerBrouillon(IDepotEcritures depot)
{
    public async Task<ResultatEcriture> Executer(string gestionnaireId, string numeroContrat, FicheBrouillon fiche,
        PrimeBrouillon? prime, CancellationToken ct)
    {
        if (!ReglesStatut.Decisions.Contains(fiche.Decision)) return new(false, "DECISION_INCONNUE");
        if (prime is not null && !ReglesStatut.Periodicites.Contains(prime.Periodicite))
            return new(false, "PERIODICITE_INCONNUE");
        if (await depot.StatutContrat(gestionnaireId, numeroContrat, ct) is { } statut && ReglesStatut.Fige(statut))
            return new(false, "STATUT_FIGE");
        return new(await depot.EnregistrerBrouillon(gestionnaireId, numeroContrat, fiche, prime, ct), null);
    }
}
