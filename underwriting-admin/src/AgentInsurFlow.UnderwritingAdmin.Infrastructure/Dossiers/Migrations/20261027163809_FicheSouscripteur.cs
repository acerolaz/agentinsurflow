using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class FicheSouscripteur : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "civilite",
                table: "souscripteur",
                type: "text",
                nullable: false,
                defaultValue: "");

            // Seed fictif (« Nom{n} », posé par les migrations précédentes) : M. pour n impair, Mme pour n pair.
            migrationBuilder.Sql("""
                UPDATE souscripteur
                SET civilite = CASE WHEN substring(nom FROM 4)::int % 2 = 1 THEN 'M.' ELSE 'Mme' END
                WHERE nom ~ '^Nom[0-9]+$'
                """);
            // Fiche du lead dans le détail du dossier (exception assumée à la minimisation, 27/10) : tout statut, borné au
            // gestionnaire par la route. La table souscripteur reste fermée au compte dossiers.
            migrationBuilder.Sql("""
                CREATE VIEW vue_fiche_souscripteur AS
                SELECT c.numero_contrat, c.gestionnaire_id,
                       s.civilite, s.nom, s.prenom, s.adresse, s.code_postal, s.telephone, s.email,
                       v.marque, v.modele, v.immatriculation, v.puissance_fiscale_cv, v.type_usage
                FROM contrat c
                JOIN souscripteur s ON s.id = c.souscripteur_id
                LEFT JOIN vehicule v ON v.contrat_id = c.id
                """);
            migrationBuilder.Sql("GRANT SELECT ON vue_fiche_souscripteur TO dossiers");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("DROP VIEW vue_fiche_souscripteur");
            migrationBuilder.DropColumn(
                name: "civilite",
                table: "souscripteur");
        }
    }
}
