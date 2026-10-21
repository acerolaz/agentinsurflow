using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Infrastructure.Otlp;
using Google.Protobuf;
using OpenTelemetry.Proto.Collector.Trace.V1;
using OpenTelemetry.Proto.Common.V1;
using OpenTelemetry.Proto.Resource.V1;
using OpenTelemetry.Proto.Trace.V1;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Tests;

/// <summary>Conversion OTLP → spans (adapter, octets en mémoire, sans base).</summary>
public sealed class OtlpVersSpansTests
{
    private static readonly byte[] TraceId = Convert.FromHexString("0af7651916cd43dd8448eb211c80319c");
    private static readonly byte[] SpanId = Convert.FromHexString("b7ad6b7169203331");
    private static readonly DateTimeOffset Recu = new(2026, 10, 20, 9, 0, 0, TimeSpan.Zero);

    private static KeyValue Cle(string cle, AnyValue valeur) => new() { Key = cle, Value = valeur };

    private static ExportTraceServiceRequest Requete(string? service, Span span)
    {
        var ressource = new Resource();
        if (service is not null)
        {
            ressource.Attributes.Add(Cle("service.name", new AnyValue { StringValue = service }));
        }
        var lot = new ResourceSpans { Resource = ressource };
        var portee = new ScopeSpans { Scope = new InstrumentationScope { Name = "portee", Version = "1.2" } };
        portee.Spans.Add(span);
        lot.ScopeSpans.Add(portee);
        var requete = new ExportTraceServiceRequest();
        requete.ResourceSpans.Add(lot);
        return requete;
    }

    private static Span UnSpan() => new()
    {
        TraceId = ByteString.CopyFrom(TraceId),
        SpanId = ByteString.CopyFrom(SpanId),
        Name = "rag.recherche",
        Kind = Span.Types.SpanKind.Server,
        StartTimeUnixNano = 1_000_000_000,
        EndTimeUnixNano = 1_250_000_000,
        Status = new Status { Code = Status.Types.StatusCode.Error, Message = "boum" },
        Attributes = { Cle("rag.statut", new AnyValue { StringValue = "ok" }), Cle("rag.articles", new AnyValue { IntValue = 3 }) },
    };

    [Fact]
    public void Otlp_vers_spans_identifiants_hexa_et_service_name()
    {
        var span = UnSpan();
        span.ParentSpanId = ByteString.CopyFrom(Convert.FromHexString("00f067aa0ba902b7"));

        var resultat = Assert.Single(OtlpVersSpans.Convertir(Requete("rag", span), Recu));

        Assert.Equal("0af7651916cd43dd8448eb211c80319c", resultat.TraceId);
        Assert.Equal("b7ad6b7169203331", resultat.SpanId);
        Assert.Equal("00f067aa0ba902b7", resultat.ParentSpanId);
        Assert.Equal("rag", resultat.ServiceName);
        Assert.Equal("portee", resultat.ScopeName);
        Assert.Equal(2, resultat.Kind);
        Assert.Equal(2, resultat.StatusCode);
        Assert.Equal(250.0, resultat.DureeMs);
        Assert.Equal(Recu, resultat.RecuLe);
        using var attributs = JsonDocument.Parse(resultat.Attributes);
        Assert.Equal("ok", attributs.RootElement.GetProperty("rag.statut").GetString());
        Assert.Equal(3, attributs.RootElement.GetProperty("rag.articles").GetInt64());
    }

    [Fact]
    public void Span_racine_n_a_pas_de_parent()
    {
        var resultat = Assert.Single(OtlpVersSpans.Convertir(Requete("rag", UnSpan()), Recu));

        Assert.Null(resultat.ParentSpanId);
    }

    [Fact]
    public void Otlp_sans_service_name_donne_inconnu()
    {
        Assert.Equal("inconnu", Assert.Single(OtlpVersSpans.Convertir(Requete(null, UnSpan()), Recu)).ServiceName);
        Assert.Equal("inconnu", Domain.ReglesTraces.NomDeService("  "));
    }

    [Fact]
    public void Identifiant_de_mauvaise_longueur_est_refuse()
    {
        var span = UnSpan();
        span.SpanId = ByteString.CopyFrom([1, 2, 3]);

        Assert.Throws<FormatException>(() => OtlpVersSpans.Convertir(Requete("rag", span), Recu));
    }

    [Fact]
    public void Horodatage_hors_plage_est_refuse()
    {
        var span = UnSpan();
        span.EndTimeUnixNano = ulong.MaxValue; // négatif une fois casté en long

        Assert.Throws<FormatException>(() => OtlpVersSpans.Convertir(Requete("rag", span), Recu));
    }

    [Fact]
    public void Octets_invalides_sont_refuses()
    {
        Assert.Throws<FormatException>(() => OtlpVersSpans.Convertir(new byte[] { 0x0a, 0xff, 0x01 }, Recu));
    }

    [Fact]
    public void AnyValue_tableau_et_kvlist_en_json()
    {
        var tableau = new AnyValue { ArrayValue = new ArrayValue { Values = { new AnyValue { IntValue = 1 }, new AnyValue { StringValue = "b" } } } };
        var liste = new AnyValue
        {
            KvlistValue = new KeyValueList { Values = { Cle("a", new AnyValue { BoolValue = true }), Cle("t", tableau), Cle("d", new AnyValue { DoubleValue = 0.5 }) } },
        };
        var span = UnSpan();
        span.Attributes.Add(Cle("liste", liste));
        span.Attributes.Add(Cle("octets", new AnyValue { BytesValue = ByteString.CopyFrom([1, 2]) }));
        span.Attributes.Add(Cle("vide", new AnyValue()));

        var resultat = Assert.Single(OtlpVersSpans.Convertir(Requete("rag", span), Recu));

        using var attributs = JsonDocument.Parse(resultat.Attributes);
        var racine = attributs.RootElement;
        Assert.Equal("""{"a":true,"t":[1,"b"],"d":0.5}""", racine.GetProperty("liste").GetRawText());
        Assert.Equal("AQI=", racine.GetProperty("octets").GetString());
        Assert.Equal(JsonValueKind.Null, racine.GetProperty("vide").ValueKind);
    }

    [Fact]
    public void Evenements_et_liens_en_json()
    {
        var span = UnSpan();
        span.Events.Add(new Span.Types.Event { TimeUnixNano = 1_100_000_000, Name = "cache", Attributes = { Cle("hit", new AnyValue { BoolValue = false }) } });
        span.Links.Add(new Span.Types.Link { TraceId = ByteString.CopyFrom(TraceId), SpanId = ByteString.CopyFrom(SpanId) });

        var resultat = Assert.Single(OtlpVersSpans.Convertir(Requete("rag", span), Recu));

        using var evenements = JsonDocument.Parse(resultat.Events);
        Assert.Equal("cache", evenements.RootElement[0].GetProperty("name").GetString());
        using var liens = JsonDocument.Parse(resultat.Links);
        Assert.Equal("b7ad6b7169203331", liens.RootElement[0].GetProperty("span_id").GetString());
    }
}
