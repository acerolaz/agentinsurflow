using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class ContratAccepte : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // Contrat imprimé (exception assumée à la minimisation) : parties au contrat des seuls contrats ACCEPTE,
            // sans e-mail ni téléphone. La table souscripteur reste fermée au compte dossiers ; la vue s'exécute avec
            // les droits de son propriétaire (migrateur).
            // ponytail: un véhicule par contrat (seed) ; LATERAL … LIMIT 1 si un contrat en porte plusieurs.
            migrationBuilder.Sql("""
                CREATE VIEW vue_contrat_accepte AS
                SELECT c.numero_contrat, c.gestionnaire_id,
                       s.nom, s.prenom, s.date_naissance, s.adresse, s.code_postal, s.permis_numero, s.permis_date_obtention,
                       v.marque, v.modele, v.immatriculation, v.puissance_fiscale_cv, v.type_usage
                FROM contrat c
                JOIN souscripteur s ON s.id = c.souscripteur_id
                LEFT JOIN vehicule v ON v.contrat_id = c.id
                WHERE c.statut = 'ACCEPTE'
                """);
            migrationBuilder.Sql("GRANT SELECT ON vue_contrat_accepte TO dossiers");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("DROP VIEW vue_contrat_accepte");
        }
    }
}
