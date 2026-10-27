using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class Relances : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "relance",
                columns: table => new
                {
                    numero_contrat = table.Column<string>(type: "text", nullable: false),
                    rang = table.Column<int>(type: "integer", nullable: false),
                    texte = table.Column<string>(type: "text", nullable: false),
                    pieces = table.Column<string>(type: "jsonb", nullable: false),
                    envoyee_le = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()"),
                    envoyee_par = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_relance", x => new { x.numero_contrat, x.rang });
                    table.ForeignKey(
                        name: "fk_relance_contrat_numero_contrat",
                        column: x => x.numero_contrat,
                        principalTable: "contrat",
                        principalColumn: "numero_contrat",
                        onDelete: ReferentialAction.Cascade);
                });

            // Append-only pour le compte applicatif : une relance envoyée ne se modifie pas.
            migrationBuilder.Sql("GRANT SELECT, INSERT ON relance TO dossiers");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("REVOKE SELECT, INSERT ON relance FROM dossiers");
            migrationBuilder.DropTable(
                name: "relance");
        }
    }
}
