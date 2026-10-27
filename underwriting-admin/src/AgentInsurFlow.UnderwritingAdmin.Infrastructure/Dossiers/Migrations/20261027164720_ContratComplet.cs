using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class ContratComplet : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // Contrat imprimé sur le modèle d'Acerola (27/10) : coordonnées, permis, détail du véhicule et garanties.
            // Colonnes ajoutées en fin de vue (CREATE OR REPLACE n'accepte que l'ajout).
            migrationBuilder.Sql("""
                CREATE OR REPLACE VIEW vue_contrat_accepte AS
                SELECT c.numero_contrat, c.gestionnaire_id,
                       s.nom, s.prenom, s.date_naissance, s.adresse, s.code_postal, s.permis_numero, s.permis_date_obtention,
                       v.marque, v.modele, v.immatriculation, v.puissance_fiscale_cv, v.type_usage,
                       s.permis_pays, s.telephone, s.email,
                       v.version, v.vin, v.date1re_mise_circulation, v.mode_stationnement, v.code_postal_stationnement
                FROM contrat c
                JOIN souscripteur s ON s.id = c.souscripteur_id
                LEFT JOIN vehicule v ON v.contrat_id = c.id
                WHERE c.statut = 'ACCEPTE'
                """);
            migrationBuilder.Sql("""
                CREATE OR REPLACE VIEW vue_fiche_souscripteur AS
                SELECT c.numero_contrat, c.gestionnaire_id,
                       s.civilite, s.nom, s.prenom, s.adresse, s.code_postal, s.telephone, s.email,
                       v.marque, v.modele, v.immatriculation, v.puissance_fiscale_cv, v.type_usage,
                       v.version, v.vin, v.date1re_mise_circulation, v.mode_stationnement, v.code_postal_stationnement
                FROM contrat c
                JOIN souscripteur s ON s.id = c.souscripteur_id
                LEFT JOIN vehicule v ON v.contrat_id = c.id
                """);

            // Seed fictif : garanties de chaque formule (la responsabilité civile existe déjà), franchises du modèle.
            // Aucun calcul (risque, prime) ne lit ces tables. ponytail: plafond 0 = non renseigné, à poser avec le barème.
            migrationBuilder.Sql("""
                INSERT INTO garantie (id, contrat_id, type, formule, plafond_indemnisation)
                SELECT gen_random_uuid(), c.id, g.type, c.formule, 0
                FROM contrat c
                JOIN (VALUES ('protection_juridique', '{tiers,tiers_etendu,tous_risques}'::text[]),
                             ('vol_incendie_tempete', '{tiers_etendu,tous_risques}'),
                             ('bris_de_glace', '{tiers_etendu,tous_risques}'),
                             ('dommages_tous_accidents', '{tous_risques}'),
                             ('assistance_0_km', '{tous_risques}')) g(type, formules) ON c.formule = ANY (g.formules)
                WHERE NOT EXISTS (SELECT 1 FROM garantie x WHERE x.contrat_id = c.id AND x.type = g.type)
                """);
            migrationBuilder.Sql("""
                INSERT INTO franchise (id, garantie_id, garantie_liee, montant)
                SELECT gen_random_uuid(), g.id, g.type, f.montant
                FROM garantie g
                JOIN (VALUES ('protection_juridique', 0), ('vol_incendie_tempete', 300), ('bris_de_glace', 0),
                             ('dommages_tous_accidents', 450)) f(type, montant) ON f.type = g.type
                WHERE NOT EXISTS (SELECT 1 FROM franchise x WHERE x.garantie_id = g.id)
                """);
            // ponytail: une franchise par garantie (seed) ; agréger si une garantie en porte plusieurs.
            migrationBuilder.Sql("""
                CREATE VIEW vue_garanties_contrat_accepte AS
                SELECT c.numero_contrat, c.gestionnaire_id, g.type, f.montant AS franchise
                FROM contrat c
                JOIN garantie g ON g.contrat_id = c.id
                LEFT JOIN franchise f ON f.garantie_id = g.id
                WHERE c.statut = 'ACCEPTE'
                """);
            migrationBuilder.Sql("GRANT SELECT ON vue_garanties_contrat_accepte TO dossiers");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            // Les garanties ajoutées au seed restent (données fictives, sans lecteur) ; seules les vues reviennent.
            migrationBuilder.Sql("DROP VIEW vue_garanties_contrat_accepte");
            migrationBuilder.Sql("DROP VIEW vue_contrat_accepte");
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
            migrationBuilder.Sql("DROP VIEW vue_fiche_souscripteur");
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
    }
}
