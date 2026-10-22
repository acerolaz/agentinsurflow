namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

/// <summary>
/// SQL de la vue <c>vue_contrat_minimisee</c> (D39) et des droits du compte <c>dossiers</c>. Les tranches d'âge et le
/// département suivent les règles du Domain (<c>TrancheAge</c>, <c>Departement</c>) ; un test de l'adapter les compare.
/// La vue appartient à <c>migrateur</c> : <c>dossiers</c> la lit sans aucun droit sur les tables (aucun nom, aucune
/// adresse, aucun numéro de permis n'en sort).
/// </summary>
internal static class VueMinimisee
{
    public const string Creer = """
        CREATE VIEW vue_contrat_minimisee AS
        SELECT c.numero_contrat,
               c.gestionnaire_id,
               CASE WHEN date_part('year', age(current_date, s.date_naissance)) < 25 THEN '<25'
                    WHEN date_part('year', age(current_date, s.date_naissance)) < 40 THEN '25-39'
                    WHEN date_part('year', age(current_date, s.date_naissance)) < 60 THEN '40-59'
                    ELSE '60+' END AS tranche_age,
               date_part('year', age(current_date, s.permis_date_obtention))::int AS anciennete_permis_ans,
               CASE WHEN left(s.code_postal, 2) IN ('97', '98') THEN left(s.code_postal, 3)
                    ELSE left(s.code_postal, 2) END AS departement,
               COALESCE(r.crm_bonus_malus, 1)::float8 AS crm_bonus_malus,
               (SELECT count(*) FROM sinistre si WHERE si.releve_information_id = r.id)::int AS nb_sinistres,
               COALESCE(r.nb_suspensions_permis, 0) AS suspensions,
               COALESCE(r.nb_resiliations, 0) AS resiliations,
               c.formule,
               c.mis_a_jour
        FROM contrat c
        JOIN souscripteur s ON s.id = c.souscripteur_id
        LEFT JOIN releve_information r ON r.contrat_id = c.id
        """;

    /// <summary>
    /// Ajoute à la fin les faits du calcul de risque/prime, évalués à la date d'effet : ancienneté du permis en mois,
    /// véhicule le plus puissant du contrat, sinistres des 36 mois précédant la date d'effet (total et responsables).
    /// <c>CREATE OR REPLACE</c> n'autorise que l'ajout en fin : colonnes existantes inchangées, même ordre.
    /// </summary>
    public const string CreerCalcul = """
        CREATE OR REPLACE VIEW vue_contrat_minimisee AS
        SELECT c.numero_contrat,
               c.gestionnaire_id,
               CASE WHEN date_part('year', age(current_date, s.date_naissance)) < 25 THEN '<25'
                    WHEN date_part('year', age(current_date, s.date_naissance)) < 40 THEN '25-39'
                    WHEN date_part('year', age(current_date, s.date_naissance)) < 60 THEN '40-59'
                    ELSE '60+' END AS tranche_age,
               date_part('year', age(current_date, s.permis_date_obtention))::int AS anciennete_permis_ans,
               CASE WHEN left(s.code_postal, 2) IN ('97', '98') THEN left(s.code_postal, 3)
                    ELSE left(s.code_postal, 2) END AS departement,
               COALESCE(r.crm_bonus_malus, 1)::float8 AS crm_bonus_malus,
               (SELECT count(*) FROM sinistre si WHERE si.releve_information_id = r.id)::int AS nb_sinistres,
               COALESCE(r.nb_suspensions_permis, 0) AS suspensions,
               COALESCE(r.nb_resiliations, 0) AS resiliations,
               c.formule,
               c.mis_a_jour,
               c.date_effet,
               (date_part('year', age(c.date_effet, s.permis_date_obtention)) * 12
                + date_part('month', age(c.date_effet, s.permis_date_obtention)))::int AS anciennete_permis_mois,
               v.puissance_fiscale_cv,
               v.type_usage,
               (SELECT count(*) FROM sinistre si WHERE si.releve_information_id = r.id
                  AND si.date_sinistre >= c.date_effet - interval '36 months'
                  AND si.date_sinistre < c.date_effet)::int AS nb_sinistres_trois_ans,
               (SELECT count(*) FROM sinistre si WHERE si.releve_information_id = r.id
                  AND si.date_sinistre >= c.date_effet - interval '36 months'
                  AND si.date_sinistre < c.date_effet
                  AND si.taux_responsabilite > 0)::int AS nb_sinistres_responsables_trois_ans
        FROM contrat c
        JOIN souscripteur s ON s.id = c.souscripteur_id
        LEFT JOIN releve_information r ON r.contrat_id = c.id
        LEFT JOIN LATERAL (SELECT puissance_fiscale_cv, type_usage FROM vehicule
                           WHERE contrat_id = c.id ORDER BY puissance_fiscale_cv DESC LIMIT 1) v ON true
        """;

    public const string Droits = """
        GRANT USAGE ON SCHEMA public TO dossiers;
        GRANT SELECT ON vue_contrat_minimisee TO dossiers
        """;

    public const string Supprimer = "DROP VIEW IF EXISTS vue_contrat_minimisee";
}
