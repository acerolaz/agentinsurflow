using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class VueCalcul : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql(VueMinimisee.CreerCalcul);
            migrationBuilder.Sql(VueMinimisee.Droits);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            // CREATE OR REPLACE VIEW ne retire pas de colonne : on supprime la vue puis on recrée celle de VueEtDroits.
            migrationBuilder.Sql(VueMinimisee.Supprimer);
            migrationBuilder.Sql(VueMinimisee.Creer);
            migrationBuilder.Sql(VueMinimisee.Droits);
        }
    }
}
