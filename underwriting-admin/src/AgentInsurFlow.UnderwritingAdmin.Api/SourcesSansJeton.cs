using System.Net;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.HttpOverrides;

namespace AgentInsurFlow.UnderwritingAdmin.Api;

/// <summary>Exigence de la route <c>/v1/traces</c> (règle S3-21) : une source locale sans jeton, sinon le rôle <c>Telemetrie</c>.</summary>
internal sealed class SourceSansJetonOuTelemetrie : IAuthorizationRequirement;

/// <summary>
/// Sans jeton, passe seulement une requête <b>sans</b> <c>X-Forwarded-For</c> (elle ne vient pas de la gateway)
/// dont l'adresse source est dans <c>Otlp:SourcesSansJeton</c> (CIDR séparés par des virgules ; défaut : loopback).
/// Tout le reste doit porter un jeton avec le rôle <c>Telemetrie</c>.
/// </summary>
internal sealed class SourcesSansJetonHandler(IConfiguration configuration) : AuthorizationHandler<SourceSansJetonOuTelemetrie>
{
    private const string Defaut = "127.0.0.1/32,::1/128";

    private readonly IPNetwork[] _reseaux = (configuration["Otlp:SourcesSansJeton"] ?? Defaut)
        .Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)
        .Select(cidr => IPNetwork.TryParse(cidr, out var reseau) ? reseau
            : throw new InvalidOperationException($"Otlp:SourcesSansJeton : CIDR invalide « {cidr} »"))
        .ToArray();

    protected override Task HandleRequirementAsync(AuthorizationHandlerContext context, SourceSansJetonOuTelemetrie requirement)
    {
        if (context.User.IsInRole("Telemetrie") || (context.Resource is HttpContext http && EstSourceLocale(http)))
        {
            context.Succeed(requirement);
        }
        return Task.CompletedTask;
    }

    private bool EstSourceLocale(HttpContext http)
    {
        if (http.Request.Headers.ContainsKey("X-Forwarded-For") || http.Connection.RemoteIpAddress is not { } ip)
        {
            return false;
        }
        var source = ip.IsIPv4MappedToIPv6 ? ip.MapToIPv4() : ip;
        return _reseaux.Any(r => r.Contains(source));
    }
}
