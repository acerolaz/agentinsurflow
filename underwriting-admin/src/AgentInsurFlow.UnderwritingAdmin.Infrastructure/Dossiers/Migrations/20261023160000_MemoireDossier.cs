using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable
#pragma warning disable CA1861 // index composés générés par EF : appelés une fois

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class MemoireDossier : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
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
                });

            migrationBuilder.CreateTable(
                name: "rapport_agent",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    numero_contrat = table.Column<string>(type: "text", nullable: false),
                    agent = table.Column<string>(type: "text", nullable: false),
                    tentative = table.Column<int>(type: "integer", nullable: false),
                    rapport = table.Column<string>(type: "jsonb", nullable: false),
                    mode = table.Column<string>(type: "text", nullable: false),
                    cause = table.Column<string>(type: "text", nullable: true),
                    version_prompt = table.Column<string>(type: "text", nullable: false),
                    trace_id = table.Column<string>(type: "text", nullable: false),
                    cree_le = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false, defaultValueSql: "now()")
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_rapport_agent", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "section_etat",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    numero_contrat = table.Column<string>(type: "text", nullable: false),
                    section = table.Column<string>(type: "text", nullable: false),
                    tentative = table.Column<int>(type: "integer", nullable: false),
                    contenu = table.Column<string>(type: "jsonb", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_section_etat", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "tour_pilotage",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    numero_contrat = table.Column<string>(type: "text", nullable: false),
                    tentative = table.Column<int>(type: "integer", nullable: false),
                    tour = table.Column<int>(type: "integer", nullable: false),
                    outil_appele = table.Column<string>(type: "text", nullable: false),
                    precondition = table.Column<string>(type: "text", nullable: false),
                    mode = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_tour_pilotage", x => x.id);
                });

            migrationBuilder.CreateIndex(
                name: "ix_rapport_agent_numero_contrat_agent_tentative_trace_id",
                table: "rapport_agent",
                columns: new[] { "numero_contrat", "agent", "tentative", "trace_id" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "ix_section_etat_numero_contrat_section_tentative",
                table: "section_etat",
                columns: new[] { "numero_contrat", "section", "tentative" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "ix_tour_pilotage_numero_contrat_tentative_tour",
                table: "tour_pilotage",
                columns: new[] { "numero_contrat", "tentative", "tour" },
                unique: true);

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
                name: "etat_dossier");

            migrationBuilder.DropTable(
                name: "rapport_agent");

            migrationBuilder.DropTable(
                name: "section_etat");

            migrationBuilder.DropTable(
                name: "tour_pilotage");
        }
    }
}
