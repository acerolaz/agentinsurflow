using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class Seed : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // Dossiers synthétiques des deux gestionnaires (oid lus dans l'environnement, jamais commités).
            migrationBuilder.Sql(SeedDossiers.Sql(
                Environment.GetEnvironmentVariable("SEED_GESTIONNAIRE_A"),
                Environment.GetEnvironmentVariable("SEED_GESTIONNAIRE_B")));
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            // Les dossiers de démonstration ne se retirent pas : un `down` détruirait des données saisies depuis.
        }
    }
}
