namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>
/// Fichier d'une pièce déclarée sur un contrat du gestionnaire ; <c>null</c> pour un contrat inexistant ou à un autre
/// (même réponse : BOLA) et pour une pièce non déclarée. Réservé au gestionnaire : jamais au cluster ni à un LLM.
/// </summary>
public sealed class ConsulterPiece(IDepotDossiers depot, IStockPieces stock)
{
    public async Task<byte[]?> Executer(string gestionnaireId, string numeroContrat, string type, CancellationToken ct)
    {
        var pieces = await depot.ListerPieces(gestionnaireId, numeroContrat, ct);
        return pieces is not null && pieces.Any(p => p.Type == type) ? stock.Lire(type) : null;
    }
}
