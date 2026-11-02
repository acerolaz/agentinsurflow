namespace AgentInsurFlow.Gateway.Api;

/// <summary>Lecture seule : des octets déjà lus, puis la suite du flux d'origine.</summary>
internal sealed class FluxPrefixe(byte[] prefixe, Stream suite) : Stream
{
    private int _position;

    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }

    public override async ValueTask<int> ReadAsync(Memory<byte> tampon, CancellationToken cancellationToken = default)
    {
        if (_position >= prefixe.Length)
        {
            return await suite.ReadAsync(tampon, cancellationToken);
        }
        var n = Math.Min(tampon.Length, prefixe.Length - _position);
        prefixe.AsMemory(_position, n).CopyTo(tampon);
        _position += n;
        return n;
    }

    public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken) =>
        ReadAsync(buffer.AsMemory(offset, count), cancellationToken).AsTask();

    public override int Read(byte[] buffer, int offset, int count) => ReadAsync(buffer, offset, count).GetAwaiter().GetResult();

    public override void Flush()
    {
    }

    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();

    public override void SetLength(long value) => throw new NotSupportedException();

    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            suite.Dispose();
        }
        base.Dispose(disposing);
    }
}
