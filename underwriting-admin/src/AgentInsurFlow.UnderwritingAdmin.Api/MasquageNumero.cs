using System.Diagnostics;
using System.Text.RegularExpressions;
using OpenTelemetry;

namespace AgentInsurFlow.UnderwritingAdmin.Api;

/// <summary>
/// Le numéro de contrat (<c>AIF-AAAA-NNNNNN</c>) ne doit pas partir dans la télémétrie : il est remplacé
/// par <c>{numero_contrat}</c> dans les spans HTTP (#65). Une copie par service (solutions indépendantes).
/// </summary>
public static partial class MasquageNumero
{
    private static readonly string[] Etiquettes = ["url.path", "url.full", "url.query", "http.target", "http.url"];

    [GeneratedRegex(@"AIF-\d{4}-\d{6}")]
    private static partial Regex Numero();

    public static string Masquer(string texte) => Numero().Replace(texte, "{numero_contrat}");

    public static void Appliquer(Activity activite)
    {
        foreach (var etiquette in Etiquettes)
        {
            if (activite.GetTagItem(etiquette) is string valeur)
            {
                activite.SetTag(etiquette, Masquer(valeur));
            }
        }
        activite.DisplayName = Masquer(activite.DisplayName);
    }

    /// <summary>
    /// Masque chaque span à sa fin (serveur, client, quelle que soit l'instrumentation), avant les exportateurs
    /// enregistrés après lui : à ajouter en premier dans <c>WithTracing</c>, avant <c>UseAzureMonitor</c>.
    /// </summary>
    public sealed class Processeur : BaseProcessor<Activity>
    {
        public override void OnEnd(Activity data) => Appliquer(data);
    }
}
