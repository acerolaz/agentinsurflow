using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class VueEtDroits : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // Vue minimisée (D39) puis droits du compte `dossiers` : SELECT sur la vue seulement.
            migrationBuilder.Sql(VueMinimisee.Creer);
            migrationBuilder.Sql(VueMinimisee.Droits);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("REVOKE ALL ON vue_contrat_minimisee FROM dossiers");
            migrationBuilder.Sql(VueMinimisee.Supprimer);
        }
    }
}
