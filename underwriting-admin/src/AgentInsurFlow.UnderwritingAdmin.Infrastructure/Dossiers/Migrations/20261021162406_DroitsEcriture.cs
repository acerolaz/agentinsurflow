using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class DroitsEcriture : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // Droits d'écriture du compte `dossiers`, au plus juste : sur `contrat`, SELECT des seules colonnes du filtre BOLA
            // (jamais la table entière) et UPDATE de statut et mis_a_jour ; souscripteur reste inaccessible.
            migrationBuilder.Sql("GRANT SELECT (id, numero_contrat, gestionnaire_id), UPDATE (statut, mis_a_jour) ON contrat TO dossiers");
            migrationBuilder.Sql("GRANT SELECT, INSERT, UPDATE ON decision, prime TO dossiers");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("REVOKE SELECT, INSERT, UPDATE ON decision, prime FROM dossiers");
            migrationBuilder.Sql("REVOKE SELECT (id, numero_contrat, gestionnaire_id), UPDATE (statut, mis_a_jour) ON contrat FROM dossiers");
        }
    }
}
