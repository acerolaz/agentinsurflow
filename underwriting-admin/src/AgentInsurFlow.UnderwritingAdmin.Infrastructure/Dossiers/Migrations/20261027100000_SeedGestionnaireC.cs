using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class SeedGestionnaireC : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // Gestionnaire C : l'identité de la CI et ses témoins BOLA (dossiers 7 à 9), oid lu dans l'environnement.
            var c = Environment.GetEnvironmentVariable("SEED_GESTIONNAIRE_C");
            migrationBuilder.Sql(SeedDossiers.SqlC(c));
            migrationBuilder.Sql(SeedDossiers.SqlPiecesC(c));
            // Dossier « refus » du gestionnaire A (démo K1, #100) : le barème le refuse (R01).
            migrationBuilder.Sql(SeedDossiers.SqlRefusA(Environment.GetEnvironmentVariable("SEED_GESTIONNAIRE_A")));
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            // Les dossiers de démonstration ne se retirent pas : un `down` détruirait des données saisies depuis.
        }
    }
}
