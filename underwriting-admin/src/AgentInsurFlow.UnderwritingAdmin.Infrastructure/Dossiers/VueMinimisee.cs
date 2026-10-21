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

    public const string Droits = """
        GRANT USAGE ON SCHEMA public TO dossiers;
        GRANT SELECT ON vue_contrat_minimisee TO dossiers
        """;

    public const string Supprimer = "DROP VIEW IF EXISTS vue_contrat_minimisee";
}
