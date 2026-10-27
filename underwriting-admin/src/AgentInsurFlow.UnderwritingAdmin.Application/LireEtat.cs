using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Progression d'un dossier pour l'espace gestionnaire : seules les sections lisibles sortent ; <c>null</c> = 404 (BOLA).</summary>
public sealed class LireEtat(IDepotEtat depot)
{
    public async Task<EtatLu?> Executer(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
        await depot.LireEtat(gestionnaireId, numeroContrat, ct) is { } etat
            ? etat with { Sections = etat.Sections.Where(s => ReglesEtat.SectionsLisibles.Contains(s.Key)).ToDictionary() }
            : null;
}
