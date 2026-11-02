using AgentInsurFlow.UnderwritingAdmin.Application;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Pieces;

/// <summary>Un PDF fictif par type, embarqué dans l'assemblage.</summary>
// ponytail: même fichier pour tous les dossiers, aucun dépôt possible ; stockage Blob par identité managée quand de vraies pièces arriveront (#141).
public sealed class StockPiecesDemo : IStockPieces
{
    public byte[]? Lire(string type)
    {
        using var flux = typeof(StockPiecesDemo).Assembly.GetManifestResourceStream($"pieces-demo/{type}.pdf");
        if (flux is null)
        {
            return null;
        }
        using var memoire = new MemoryStream();
        flux.CopyTo(memoire);
        return memoire.ToArray();
    }
}
