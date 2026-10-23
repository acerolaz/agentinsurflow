using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class PiecesDeclarees : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateOnly>(
                name: "date_emission",
                table: "piece_justificative",
                type: "date",
                nullable: false,
                defaultValue: new DateOnly(1, 1, 1));

            migrationBuilder.AddColumn<DateTimeOffset>(
                name: "declaree_le",
                table: "piece_justificative",
                type: "timestamp with time zone",
                nullable: false,
                defaultValueSql: "now()");

            migrationBuilder.AddColumn<string>(
                name: "declaree_par",
                table: "piece_justificative",
                type: "text",
                nullable: false,
                defaultValue: "");

            // Le compte `dossiers` ne lit des pièces que le type et la date d'émission (jamais nom_fichier ni url_blob).
            migrationBuilder.Sql("GRANT SELECT (contrat_id, type, date_emission) ON piece_justificative TO dossiers");

            // Pièces des dossiers de démonstration (les contrats viennent de la migration Seed).
            migrationBuilder.Sql(SeedDossiers.SqlPieces(
                Environment.GetEnvironmentVariable("SEED_GESTIONNAIRE_A"),
                Environment.GetEnvironmentVariable("SEED_GESTIONNAIRE_B")));
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("REVOKE SELECT (contrat_id, type, date_emission) ON piece_justificative FROM dossiers");

            migrationBuilder.DropColumn(
                name: "date_emission",
                table: "piece_justificative");

            migrationBuilder.DropColumn(
                name: "declaree_le",
                table: "piece_justificative");

            migrationBuilder.DropColumn(
                name: "declaree_par",
                table: "piece_justificative");
        }
    }
}
