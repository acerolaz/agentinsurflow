using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class Observations : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "observations",
                table: "contrat",
                type: "text",
                nullable: true);

            migrationBuilder.AddCheckConstraint(
                name: "ck_contrat_observations_longueur",
                table: "contrat",
                sql: "char_length(observations) <= 2000");

            // CREATE OR REPLACE : la vue gagne `observations` en dernière colonne ; les droits existants sont conservés.
            migrationBuilder.Sql(VueMinimisee.CreerObservations);
            migrationBuilder.Sql(VueMinimisee.Droits);
            // Le compte `dossiers` lit le statut (règle « statut figé ») et écrit les seules observations en plus de statut/mis_a_jour.
            migrationBuilder.Sql("GRANT SELECT (statut), UPDATE (observations) ON contrat TO dossiers");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("REVOKE SELECT (statut), UPDATE (observations) ON contrat FROM dossiers");
            // La vue dépend de la colonne : on la supprime, puis on recrée celle de VueCalcul.
            migrationBuilder.Sql(VueMinimisee.Supprimer);

            migrationBuilder.DropCheckConstraint(
                name: "ck_contrat_observations_longueur",
                table: "contrat");

            migrationBuilder.DropColumn(
                name: "observations",
                table: "contrat");

            migrationBuilder.Sql(VueMinimisee.CreerCalcul);
            migrationBuilder.Sql(VueMinimisee.Droits);
        }
    }
}
