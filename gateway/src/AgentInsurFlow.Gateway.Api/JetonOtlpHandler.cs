using System.Net.Http.Headers;
using Azure;
using Azure.Core;
using Azure.Identity;

namespace AgentInsurFlow.Gateway.Api;

/// <summary>
/// Pose le jeton d'application de la gateway (rôle <c>Telemetrie</c> d'underwriting-admin) sur l'export OTLP.
/// Sans portée (local) : aucun jeton. Credential en échec : l'export part sans jeton (401 côté récepteur),
/// jamais d'exception ni de blocage, jamais de détail ni de jeton journalisé.
/// L'exporteur OTLP/HTTP envoie en synchrone (<c>HttpClient.Send</c>) : les deux voies sont gérées.
/// </summary>
internal sealed class JetonOtlpHandler(Func<TokenCredential> credential, string? portee) : DelegatingHandler
{
    protected override HttpResponseMessage Send(HttpRequestMessage requete, CancellationToken ct)
    {
        if (!string.IsNullOrEmpty(portee))
        {
            try
            {
                Poser(requete, credential().GetToken(new TokenRequestContext([portee]), ct));
            }
            catch (Exception e) when (EstEchecJeton(e))
            {
                // sans jeton : le récepteur répondra 401
            }
        }
        return base.Send(requete, ct);
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage requete, CancellationToken ct)
    {
        if (!string.IsNullOrEmpty(portee))
        {
            try
            {
                Poser(requete, await credential().GetTokenAsync(new TokenRequestContext([portee]), ct));
            }
            catch (Exception e) when (EstEchecJeton(e))
            {
                // sans jeton : le récepteur répondra 401
            }
        }
        return await base.SendAsync(requete, ct);
    }

    private static bool EstEchecJeton(Exception e) => e is AuthenticationFailedException or RequestFailedException or HttpRequestException;

    private static void Poser(HttpRequestMessage requete, AccessToken jeton) =>
        requete.Headers.Authorization = new AuthenticationHeaderValue("Bearer", jeton.Token);
}
