namespace AgentInsurFlow.UnderwritingAdmin.Application;

/// <summary>Fichiers des pièces justificatives, par type ; <c>null</c> si le stock n'en a pas.</summary>
public interface IStockPieces
{
    byte[]? Lire(string type);
}
