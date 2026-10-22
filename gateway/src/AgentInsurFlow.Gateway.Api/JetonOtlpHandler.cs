using System.Net.Http.Headers;
using Azure;
using Azure.Core;
using Azure.Identity;

namespace AgentInsurFlow.Gateway.Api;

/// <summary>
/// Pose le jeton d'application de la gateway (rôle <c>Telemetrie</c> d'underwriting-admin) sur l'export OTLP.
/// Sans portée (local) : aucun jeton. Credential en échec : l'export part sans jeton (401 côté récepteur),
/// jamais d'exception ni de blocage, jamais de détail ni de jeton journalisé.
/// L'exporteur OTLP/HTTP envoie en synchrone (<c>HttpClient.Send</c>) : un seul <see cref="Poser"/> synchrone sert les deux voies.
/// </summary>
internal sealed class JetonOtlpHandler(Func<TokenCredential> credential, string? portee) : DelegatingHandler
{
    protected override HttpResponseMessage Send(HttpRequestMessage requete, CancellationToken ct)
    {
        Poser(requete, ct);
        return base.Send(requete, ct);
    }

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage requete, CancellationToken ct)
    {
        Poser(requete, ct); // le credential met le jeton en cache : l'appel bloquant est rare
        return base.SendAsync(requete, ct);
    }

    private void Poser(HttpRequestMessage requete, CancellationToken ct)
    {
        if (string.IsNullOrEmpty(portee))
        {
            return;
        }
        try
        {
            requete.Headers.Authorization = new AuthenticationHeaderValue(
                "Bearer", credential().GetToken(new TokenRequestContext([portee]), ct).Token);
        }
        catch (Exception e) when (e is AuthenticationFailedException or RequestFailedException or HttpRequestException)
        {
            // sans jeton : le récepteur répondra 401
        }
    }
}
