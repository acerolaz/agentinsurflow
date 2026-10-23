using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable
#pragma warning disable CA1861 // clés et index composés générés par EF : appelés une fois

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class MemoireDossier : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddUniqueConstraint(
                name: "ak_contrat_numero_contrat",
                table: "contrat",
                column: "numero_contrat");

            migrationBuilder.CreateTable(
                name: "etat_dossier",
                columns: table => new
                {
                    numero_contrat = table.Column<string>(type: "text", nullable: false),
                    version_schema = table.Column<int>(type: "integer", nullable: false),
                    statut_parcours = table.Column<string>(type: "text", nullable: false),
                    tentative = table.Column<int>(type: "integer", nullable: false),
                    nb_relances = table.Column<int>(type: "integer", nullable: false),
                    maj_le = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_etat_dossier", x => x.numero_contrat);
                    table.ForeignKey(
                        name: "fk_etat_dossier_contrat_numero_contrat",
                        column: x => x.numero_contrat,
                        principalTable: "contrat",
                        principalColumn: "numero_contrat",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "rapport_agent",
                columns: table => new
                {
                    numero_contrat = table.Column<string>(type: "text", nullable: false),
                    agent = table.Column<string>(type: "text", nullable: false),
                    tentative = table.Column<int>(type: "integer", nullable: false),
                    trace_id = table.Column<string>(type: "text", nullable: false),
                    rapport = table.Column<string>(type: "jsonb", nullable: false),
                    mode = table.Column<string>(type: "text", nullable: false),
                    cause = table.Column<string>(type: "text", nullable: true),
                    version_prompt = table.Column<string>(type: "text", nullable: false),
                    cree_le = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_rapport_agent", x => new { x.numero_contrat, x.agent, x.tentative, x.trace_id });
                    table.ForeignKey(
                        name: "fk_rapport_agent_etat_dossier_numero_contrat",
                        column: x => x.numero_contrat,
                        principalTable: "etat_dossier",
                        principalColumn: "numero_contrat",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "section_etat",
                columns: table => new
                {
                    numero_contrat = table.Column<string>(type: "text", nullable: false),
                    section = table.Column<string>(type: "text", nullable: false),
                    tentative = table.Column<int>(type: "integer", nullable: false),
                    contenu = table.Column<string>(type: "jsonb", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_section_etat", x => new { x.numero_contrat, x.section, x.tentative });
                    table.ForeignKey(
                        name: "fk_section_etat_etat_dossier_numero_contrat",
                        column: x => x.numero_contrat,
                        principalTable: "etat_dossier",
                        principalColumn: "numero_contrat",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "tour_pilotage",
                columns: table => new
                {
                    numero_contrat = table.Column<string>(type: "text", nullable: false),
                    tentative = table.Column<int>(type: "integer", nullable: false),
                    tour = table.Column<int>(type: "integer", nullable: false),
                    outil_appele = table.Column<string>(type: "text", nullable: false),
                    precondition = table.Column<string>(type: "text", nullable: false),
                    mode = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_tour_pilotage", x => new { x.numero_contrat, x.tentative, x.tour });
                    table.ForeignKey(
                        name: "fk_tour_pilotage_etat_dossier_numero_contrat",
                        column: x => x.numero_contrat,
                        principalTable: "etat_dossier",
                        principalColumn: "numero_contrat",
                        onDelete: ReferentialAction.Cascade);
                });

            // Le compte `dossiers` : état et sections en upsert (SELECT, INSERT, UPDATE) ; rapports et tours en ajout seul.
            migrationBuilder.Sql("GRANT SELECT, INSERT, UPDATE ON etat_dossier, section_etat TO dossiers");
            migrationBuilder.Sql("GRANT SELECT, INSERT ON rapport_agent, tour_pilotage TO dossiers");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("REVOKE SELECT, INSERT ON rapport_agent, tour_pilotage FROM dossiers");
            migrationBuilder.Sql("REVOKE SELECT, INSERT, UPDATE ON etat_dossier, section_etat FROM dossiers");

            migrationBuilder.DropTable(
                name: "rapport_agent");

            migrationBuilder.DropTable(
                name: "section_etat");

            migrationBuilder.DropTable(
                name: "tour_pilotage");

            migrationBuilder.DropTable(
                name: "etat_dossier");

            migrationBuilder.DropUniqueConstraint(
                name: "ak_contrat_numero_contrat",
                table: "contrat");
        }
    }
}
