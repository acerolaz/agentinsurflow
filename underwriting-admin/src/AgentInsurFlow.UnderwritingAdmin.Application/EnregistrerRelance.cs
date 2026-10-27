using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Relance modifiable par le gestionnaire, enregistrée et tracée comme envoyée (sans e-mail avant #123).</summary>
public sealed class EnregistrerRelance(IDepotRelances depot)
{
    // ponytail: compte puis insère sans verrou ; deux envois simultanés se heurtent à la clé (numero_contrat, rang) : le second a 409
    public async Task<ResultatRelance> Executer(string gestionnaireId, string numeroContrat, string texte,
        IReadOnlyList<string> pieces, CancellationToken ct)
    {
        if (await depot.Situation(gestionnaireId, numeroContrat, ct) is not { } situation) return new(null, null);
        if (ReglesRelance.Refus(situation, texte, pieces) is { } refus) return new(null, refus);
        return await depot.Ajouter(gestionnaireId, numeroContrat, texte, pieces, ct) is { } rang
            ? new(rang, null)
            : new(null, ReglesRelance.Concurrente);
    }
}
