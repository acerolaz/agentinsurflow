using AgentInsurFlow.UnderwritingAdmin.Application;
using AgentInsurFlow.UnderwritingAdmin.Domain;

namespace AgentInsurFlow.UnderwritingAdmin.Application.Tests;

/// <summary>TU : on ne lit le fichier d'une pièce que si elle est déclarée sur un contrat du gestionnaire (#141).</summary>
public sealed class ConsulterPieceTests
{
    private const string Gestionnaire = "oid-a";
    private static readonly byte[] Pdf = [1, 2, 3];

    private sealed class Depot : IDepotDossiers
    {
        public Task<IReadOnlyList<PieceDeclaree>?> ListerPieces(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            Task.FromResult<IReadOnlyList<PieceDeclaree>?>(gestionnaireId == Gestionnaire && numeroContrat == "AIF-1"
                ? [new(TypesPiece.Permis, new DateOnly(2018, 6, 1))]
                : null);

        public Task<IReadOnlyList<VueContrat>> Lister(string gestionnaireId, int limit, int offset, CancellationToken ct) =>
            throw new NotSupportedException();

        public Task<VueContrat?> Trouver(string gestionnaireId, string numeroContrat, CancellationToken ct) =>
            throw new NotSupportedException();
    }

    private sealed class Stock : IStockPieces
    {
        public List<string> Lus { get; } = [];

        public byte[]? Lire(string type)
        {
            Lus.Add(type);
            return type == TypesPiece.Permis ? Pdf : null;
        }
    }

    private static Task<byte[]?> Consulter(Stock stock, string gestionnaire, string numero, string type) =>
        new ConsulterPiece(new Depot(), stock).Executer(gestionnaire, numero, type, CancellationToken.None);

    [Fact]
    public async Task Piece_declaree_rend_son_fichier() =>
        Assert.Equal(Pdf, await Consulter(new Stock(), Gestionnaire, "AIF-1", TypesPiece.Permis));

    [Fact]
    public async Task Contrat_d_un_autre_gestionnaire_ne_touche_pas_au_stock()
    {
        var stock = new Stock();
        Assert.Null(await Consulter(stock, "oid-b", "AIF-1", TypesPiece.Permis));
        Assert.Empty(stock.Lus);
    }

    [Fact]
    public async Task Piece_non_declaree_ne_touche_pas_au_stock()
    {
        var stock = new Stock();
        Assert.Null(await Consulter(stock, Gestionnaire, "AIF-1", TypesPiece.ReleveInformation));
        Assert.Empty(stock.Lus);
    }
}
