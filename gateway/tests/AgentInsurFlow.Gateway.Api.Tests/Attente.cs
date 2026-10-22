namespace AgentInsurFlow.Gateway.Api.Tests;

/// <summary>
/// Attente d'un span capturé par un <c>ActivityListener</c> : ASP.NET Core n'arrête l'activité de la requête qu'après
/// avoir rendu la réponse au client, donc <c>ActivityStopped</c> peut arriver après le retour de <c>SendAsync</c>.
/// </summary>
internal static class Attente
{
    /// <summary>L'unique élément qui vérifie <paramref name="predicat"/>, attendu jusqu'à 5 s (sinon échec explicite).</summary>
    public static async Task<T> Unique<T>(IEnumerable<T> source, Func<T, bool> predicat)
    {
        var limite = DateTime.UtcNow.AddSeconds(5);
        while (DateTime.UtcNow < limite)
        {
            var trouves = source.Where(predicat).ToList();
            if (trouves.Count > 0)
            {
                return Assert.Single(trouves);
            }
            await Task.Delay(20, TestContext.Current.CancellationToken);
        }
        return Assert.Single(source, x => predicat(x));
    }
}
