using System.Diagnostics;
using System.Text.RegularExpressions;

namespace AgentInsurFlow.Gateway.Api;

/// <summary>
/// Le numéro de contrat (<c>AIF-AAAA-NNNNNN</c>) ne doit pas partir dans la télémétrie : il est remplacé
/// par <c>{numero_contrat}</c> dans les spans HTTP (#65). Une copie par service (solutions indépendantes).
/// </summary>
public static partial class MasquageNumero
{
    private static readonly string[] Etiquettes = ["url.path", "url.full", "url.query", "http.target"];

    [GeneratedRegex(@"AIF-\d{4}-\d{6}")]
    private static partial Regex Numero();

    public static string Masquer(string texte) => Numero().Replace(texte, "{numero_contrat}");

    public static void Appliquer(Activity activite)
    {
        foreach (var etiquette in Etiquettes)
        {
            if (activite.GetTagItem(etiquette) is string valeur && Numero().IsMatch(valeur))
            {
                activite.SetTag(etiquette, Masquer(valeur));
            }
        }
        activite.DisplayName = Masquer(activite.DisplayName);
    }
}
