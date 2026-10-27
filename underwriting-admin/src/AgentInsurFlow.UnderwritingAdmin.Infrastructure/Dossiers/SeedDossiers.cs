using System.Globalization;
using System.Text;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers;

/// <summary>
/// Dossiers synthétiques (fictifs) des gestionnaires A et B (démo, contrôle BOLA) et C (identité de la CI). Les oid
/// viennent de l'environnement (SEED_GESTIONNAIRE_A / _B / _C), jamais du dépôt. Chaque INSERT est
/// <c>ON CONFLICT DO NOTHING</c> : rejouer le seed ne change rien.
/// </summary>
internal static class SeedDossiers
{
    private sealed record Dossier(int N, char Gestionnaire, DateOnly Naissance, DateOnly Permis, string CodePostal,
        string Crm, int Suspensions, int Resiliations, string Formule, int Sinistres);

    private static readonly Dossier[] Dossiers =
    [
        new(1, 'A', new(1999, 3, 14), new(2018, 6, 1), "75011", "0.90", 0, 0, "tous_risques", 0),
        new(2, 'A', new(1985, 9, 2), new(2005, 1, 20), "69003", "1.00", 0, 1, "tiers_etendu", 1),
        new(3, 'A', new(1960, 12, 25), new(1980, 5, 5), "97411", "0.50", 0, 0, "tiers", 0),
        new(4, 'B', new(2002, 7, 7), new(2020, 2, 2), "2A004", "1.25", 1, 0, "tous_risques", 2),
        new(5, 'B', new(1972, 1, 30), new(1992, 8, 18), "33000", "0.76", 0, 0, "tiers_etendu", 0),
        new(6, 'B', new(1990, 11, 11), new(2010, 4, 4), "59000", "1.00", 0, 2, "tiers", 1),
        // Migration SeedGestionnaireC : la CI (profils de 1, 5 et 6) et le dossier « refus » de A (profil de 4 : R01)
        new(7, 'C', new(1999, 3, 14), new(2018, 6, 1), "75011", "0.90", 0, 0, "tous_risques", 0),
        new(8, 'C', new(1972, 1, 30), new(1992, 8, 18), "33000", "0.76", 0, 0, "tiers_etendu", 0),
        new(9, 'C', new(1990, 11, 11), new(2010, 4, 4), "59000", "1.00", 0, 2, "tiers", 1),
        new(10, 'A', new(2002, 7, 7), new(2020, 2, 2), "2A004", "1.25", 1, 0, "tous_risques", 2),
    ];

    // Dossiers de la migration Seed (n° 1 à 6) ; les suivants viennent de SeedGestionnaireC.
    private static bool Initial(Dossier d) => d.N <= 6;

    /// <summary>Les variables d'un seed absentes laissent la base sans dossier (pas de valeur par défaut réelle).</summary>
    public static string Sql(string? gestionnaireA, string? gestionnaireB)
    {
        if (string.IsNullOrWhiteSpace(gestionnaireA) || string.IsNullOrWhiteSpace(gestionnaireB))
        {
            return "SELECT 1";
        }
        // Un oid Entra est un GUID : le reparser exclut toute chaîne qui ne le serait pas (aucune injection possible).
        var a = Oid(gestionnaireA, "SEED_GESTIONNAIRE_A");
        var b = Oid(gestionnaireB, "SEED_GESTIONNAIRE_B");
        var sql = new StringBuilder();
        foreach (var d in Dossiers.Where(Initial))
        {
            Ajouter(sql, d, d.Gestionnaire == 'A' ? a : b);
        }
        return sql.ToString();
    }

    /// <summary>Dossiers 7 à 9 du gestionnaire C (identité de la CI, témoins BOLA de l'E2E).</summary>
    public static string SqlC(string? gestionnaireC) =>
        Semer(gestionnaireC, "SEED_GESTIONNAIRE_C", d => d.Gestionnaire == 'C', pieces: false);

    /// <summary>Relevé et permis des dossiers 7 à 9 (contrats présents seulement).</summary>
    public static string SqlPiecesC(string? gestionnaireC) =>
        string.IsNullOrWhiteSpace(gestionnaireC) ? "SELECT 1" : Pieces(Dossiers.Where(d => d.Gestionnaire == 'C'));

    /// <summary>Dossier 10 du gestionnaire A, que le barème refuse (démo K1), avec ses pièces.</summary>
    public static string SqlRefusA(string? gestionnaireA) =>
        Semer(gestionnaireA, "SEED_GESTIONNAIRE_A", d => !Initial(d) && d.Gestionnaire == 'A', pieces: true);

    private static string Semer(string? gestionnaire, string variable, Func<Dossier, bool> retenu, bool pieces)
    {
        if (string.IsNullOrWhiteSpace(gestionnaire))
        {
            return "SELECT 1";
        }
        var oid = Oid(gestionnaire, variable);
        var dossiers = Dossiers.Where(retenu).ToArray();
        var sql = new StringBuilder();
        foreach (var d in dossiers)
        {
            Ajouter(sql, d, oid);
        }
        if (pieces)
        {
            sql.Append(Pieces(dossiers));
        }
        return sql.ToString();
    }

    /// <summary>
    /// Pièces déclarées des dossiers de démonstration (migration PiecesDeclarees) : relevé d'information daté de moins de
    /// 3 mois avant la date d'effet (2026-01-01) et permis, sauf le dossier n° 3, sans relevé. Insère seulement pour les contrats présents (le seed a pu tourner sans les variables SEED_*).
    /// </summary>
    public static string SqlPieces(string? gestionnaireA, string? gestionnaireB)
    {
        if (string.IsNullOrWhiteSpace(gestionnaireA) || string.IsNullOrWhiteSpace(gestionnaireB))
        {
            return "SELECT 1";
        }
        return Pieces(Dossiers.Where(Initial));
    }

    private static string Pieces(IEnumerable<Dossier> dossiers)
    {
        var sql = new StringBuilder();
        var c = CultureInfo.InvariantCulture;
        foreach (var d in dossiers)
        {
            if (d.N != DossierSansReleve)
            {
                sql.AppendLine(c, $"""
                    INSERT INTO piece_justificative (id, contrat_id, type, nom_fichier, url_blob, date_emission, declaree_le, declaree_par)
                    SELECT '{Id(9, d.N, 1)}', id, 'releve_information', 'releve-{d.N}.pdf', 'blob://demo/releve-{d.N}.pdf', '2025-11-20', '2026-10-01T08:00:00Z', 'seed'
                    FROM contrat WHERE id = '{Id(2, d.N)}'
                    ON CONFLICT DO NOTHING;
                    """);
            }
            sql.AppendLine(c, $"""
                INSERT INTO piece_justificative (id, contrat_id, type, nom_fichier, url_blob, date_emission, declaree_le, declaree_par)
                SELECT '{Id(9, d.N, 2)}', id, 'permis', 'permis-{d.N}.pdf', 'blob://demo/permis-{d.N}.pdf', '{d.Permis:yyyy-MM-dd}', '2026-10-01T08:00:00Z', 'seed'
                FROM contrat WHERE id = '{Id(2, d.N)}'
                ON CONFLICT DO NOTHING;
                """);
        }
        return sql.ToString();
    }

    private const int DossierSansReleve = 3;

    private static string Id(int genre, int n, int rang = 0) => $"{genre:x8}-0000-0000-0000-{(n * 100) + rang:x12}";

    private static string Oid(string valeur, string variable) =>
        Guid.TryParse(valeur, out var oid) ? oid.ToString("D")
            : throw new InvalidOperationException($"{variable} doit être un oid Entra (GUID) : « {valeur} » refusé");

    private static void Ajouter(StringBuilder sql, Dossier d, string gestionnaire)
    {
        var n = d.N;
        var numero = $"AIF-2026-{n:000000}";
        var c = CultureInfo.InvariantCulture;
        sql.AppendLine(c, $"""
            INSERT INTO souscripteur (id, nom, prenom, date_naissance, adresse, email, telephone, situation_familiale, permis_numero, permis_date_obtention, permis_pays, code_postal)
            VALUES ('{Id(1, n)}', 'Nom{n}', 'Prenom{n}', '{d.Naissance:yyyy-MM-dd}', '{n} rue Fictive', 'souscripteur{n}@exemple.invalid', '0600000{n:000}', 'celibataire', 'PERMIS{n:000000}', '{d.Permis:yyyy-MM-dd}', 'FR', '{d.CodePostal}')
            ON CONFLICT DO NOTHING;
            INSERT INTO contrat (id, numero_contrat, souscripteur_id, gestionnaire_id, date_effet, statut, formule, mis_a_jour)
            VALUES ('{Id(2, n)}', '{numero}', '{Id(1, n)}', '{gestionnaire}', '2026-01-01', 'actif', '{d.Formule}', '2026-10-01T08:00:00Z')
            ON CONFLICT DO NOTHING;
            INSERT INTO vehicule (id, contrat_id, immatriculation, vin, marque, modele, version, puissance_fiscale_cv, puissance_din, carburant, date1re_mise_circulation, type_usage, km_annuel_estime, mode_stationnement, code_postal_stationnement)
            VALUES ('{Id(3, n)}', '{Id(2, n)}', 'AA-{n:000}-AA', 'VIN{n:00000000000000}', 'Marque', 'Modele', 'V1', 5, 90, 'essence', '2019-05-01', 'prive', 12000, 'garage', '{d.CodePostal}')
            ON CONFLICT DO NOTHING;
            INSERT INTO releve_information (id, contrat_id, crm_bonus_malus, nb_suspensions_permis, nb_resiliations)
            VALUES ('{Id(4, n)}', '{Id(2, n)}', {d.Crm}, {d.Suspensions}, {d.Resiliations})
            ON CONFLICT DO NOTHING;
            INSERT INTO garantie (id, contrat_id, type, formule, plafond_indemnisation)
            VALUES ('{Id(5, n)}', '{Id(2, n)}', 'responsabilite_civile', '{d.Formule}', 100000000)
            ON CONFLICT DO NOTHING;
            INSERT INTO franchise (id, garantie_id, garantie_liee, montant)
            VALUES ('{Id(6, n)}', '{Id(5, n)}', 'responsabilite_civile', 300)
            ON CONFLICT DO NOTHING;
            INSERT INTO prime (id, contrat_id, prime_pure, taxe_fiscale, contribution_fgao, taxe_attentats_fgti, frais_dossier, remises, surprimes, prime_ht, prime_ttc, periodicite, date_effet, etat_validation)
            VALUES ('{Id(7, n)}', '{Id(2, n)}', 400, 40, 5, 6, 20, 0, 0, 471, 520, 'annuelle', '2026-01-01', 'valide')
            ON CONFLICT DO NOTHING;
            """);
        for (var i = 1; i <= d.Sinistres; i++)
        {
            sql.AppendLine(c, $"""
                INSERT INTO sinistre (id, releve_information_id, date_sinistre, nature, taux_responsabilite)
                VALUES ('{Id(8, n, i)}', '{Id(4, n)}', '2024-0{i}-15', 'materiel', 50)
                ON CONFLICT DO NOTHING;
                """);
        }
    }
}
