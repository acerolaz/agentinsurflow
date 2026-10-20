using System.Text.Json;
using AgentInsurFlow.UnderwritingAdmin.Domain;
using Google.Protobuf;
using OpenTelemetry.Proto.Collector.Trace.V1;
using OpenTelemetry.Proto.Common.V1;

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Otlp;

/// <summary>Requête OTLP (<c>ExportTraceServiceRequest</c>) → spans du référentiel. Les attributs sont gardés tels que reçus.</summary>
public static class OtlpVersSpans
{
    /// <summary>Décode les octets protobuf. <see cref="FormatException"/> si la requête est illisible ou porte un identifiant invalide.</summary>
    public static IReadOnlyList<Domain.Span> Convertir(ReadOnlySpan<byte> corps, DateTimeOffset recuLe)
    {
        try
        {
            return Convertir(ExportTraceServiceRequest.Parser.ParseFrom(corps), recuLe);
        }
        catch (InvalidProtocolBufferException e)
        {
            throw new FormatException("requête OTLP illisible", e);
        }
    }

    internal static IReadOnlyList<Domain.Span> Convertir(ExportTraceServiceRequest requete, DateTimeOffset recuLe)
    {
        var spans = new List<Domain.Span>();
        foreach (var lot in requete.ResourceSpans)
        {
            var service = lot.Resource?.Attributes.FirstOrDefault(a => a.Key == "service.name")?.Value?.StringValue;
            var ressource = AnyValueJson.Attributs(lot.Resource?.Attributes);
            foreach (var portee in lot.ScopeSpans)
            {
                foreach (var s in portee.Spans)
                {
                    spans.Add(new Domain.Span(
                        ReglesTraces.Hexa(s.TraceId.Span, 16),
                        ReglesTraces.Hexa(s.SpanId.Span, 8),
                        s.ParentSpanId.IsEmpty ? null : ReglesTraces.Hexa(s.ParentSpanId.Span, 8),
                        s.TraceState,
                        s.Name,
                        (int)s.Kind,
                        unchecked((long)s.StartTimeUnixNano),
                        unchecked((long)s.EndTimeUnixNano),
                        (int)(s.Status?.Code ?? 0),
                        s.Status?.Message ?? "",
                        ReglesTraces.NomDeService(service),
                        ressource,
                        AnyValueJson.Attributs(s.Attributes),
                        portee.Scope?.Name ?? "",
                        portee.Scope?.Version ?? "",
                        Evenements(s),
                        Liens(s),
                        recuLe));
                }
            }
        }
        return spans;
    }

    private static string Evenements(OpenTelemetry.Proto.Trace.V1.Span s) => AnyValueJson.Ecrire(w =>
    {
        w.WriteStartArray();
        foreach (var e in s.Events)
        {
            w.WriteStartObject();
            w.WriteNumber("time_unix_nano", e.TimeUnixNano);
            w.WriteString("name", e.Name);
            w.WritePropertyName("attributes");
            AnyValueJson.EcrireAttributs(w, e.Attributes);
            w.WriteEndObject();
        }
        w.WriteEndArray();
    });

    private static string Liens(OpenTelemetry.Proto.Trace.V1.Span s) => AnyValueJson.Ecrire(w =>
    {
        w.WriteStartArray();
        foreach (var l in s.Links)
        {
            w.WriteStartObject();
            w.WriteString("trace_id", ReglesTraces.Hexa(l.TraceId.Span, 16));
            w.WriteString("span_id", ReglesTraces.Hexa(l.SpanId.Span, 8));
            w.WriteString("trace_state", l.TraceState);
            w.WritePropertyName("attributes");
            AnyValueJson.EcrireAttributs(w, l.Attributes);
            w.WriteEndObject();
        }
        w.WriteEndArray();
    });
}

/// <summary><c>AnyValue</c> OTLP → JSON : scalaires natifs, tableau → tableau, kvlist → objet, octets → base64.</summary>
internal static class AnyValueJson
{
    public static string Ecrire(Action<Utf8JsonWriter> ecriture)
    {
        using var flux = new MemoryStream();
        using (var w = new Utf8JsonWriter(flux))
        {
            ecriture(w);
        }
        return System.Text.Encoding.UTF8.GetString(flux.ToArray());
    }

    public static string Attributs(IEnumerable<KeyValue>? attributs) => Ecrire(w => EcrireAttributs(w, attributs));

    public static string Vers(AnyValue valeur) => Ecrire(w => EcrireValeur(w, valeur));

    public static void EcrireAttributs(Utf8JsonWriter w, IEnumerable<KeyValue>? attributs)
    {
        w.WriteStartObject();
        foreach (var a in attributs ?? [])
        {
            w.WritePropertyName(a.Key);
            EcrireValeur(w, a.Value);
        }
        w.WriteEndObject();
    }

    private static void EcrireValeur(Utf8JsonWriter w, AnyValue? v)
    {
        switch (v?.ValueCase)
        {
            case AnyValue.ValueOneofCase.StringValue: w.WriteStringValue(v.StringValue); break;
            case AnyValue.ValueOneofCase.BoolValue: w.WriteBooleanValue(v.BoolValue); break;
            case AnyValue.ValueOneofCase.IntValue: w.WriteNumberValue(v.IntValue); break;
            case AnyValue.ValueOneofCase.DoubleValue when double.IsFinite(v.DoubleValue): w.WriteNumberValue(v.DoubleValue); break;
            case AnyValue.ValueOneofCase.DoubleValue: w.WriteStringValue(v.DoubleValue.ToString(System.Globalization.CultureInfo.InvariantCulture)); break; // NaN, ∞ : pas du JSON
            case AnyValue.ValueOneofCase.BytesValue: w.WriteBase64StringValue(v.BytesValue.Span); break;
            case AnyValue.ValueOneofCase.ArrayValue:
                w.WriteStartArray();
                foreach (var e in v.ArrayValue.Values)
                {
                    EcrireValeur(w, e);
                }
                w.WriteEndArray();
                break;
            case AnyValue.ValueOneofCase.KvlistValue: EcrireAttributs(w, v.KvlistValue.Values); break;
            default: w.WriteNullValue(); break;
        }
    }
}
