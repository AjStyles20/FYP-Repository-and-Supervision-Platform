"""A small, valid one-page PDF built in code, so demo downloads open in any PDF reader.

No binary file is kept in the repository: seed_demo calls demo_pdf() and stores the result as an
ordinary uploaded file under MEDIA_ROOT. Text is drawn in Helvetica, one line per entry.
"""


def _escape(text):
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def demo_pdf(title, lines=()):
    """Return the bytes of an A4 PDF with `title` in bold-sized text and `lines` beneath it."""
    commands = ["BT", "/F1 18 Tf", "72 770 Td", f"({_escape(title)}) Tj", "/F1 11 Tf", "0 -28 Td"]
    for line in ("Synthetic demonstration file. Not a real student document.", *lines):
        commands += [f"({_escape(line)}) Tj", "0 -16 Td"]
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def demo_png(width=480, height=300):
    """A valid PNG that looks like a simple app screen (a dark header bar, a sidebar and content
    rows), built in code like demo_pdf(), so demo screenshots need no committed image files."""
    import struct
    import zlib

    dark, accent, light, line = (32, 32, 32), (160, 0, 0), (246, 247, 249), (215, 218, 224)
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            if y < 56:
                colour = accent if x < 56 else dark
            elif x < 150:
                colour = line if (y - 80) % 40 < 16 and 16 < x < 134 else light
            else:
                colour = line if (y - 90) % 48 < 14 and 180 < x < width - 30 else light
            row += bytes(colour)
        rows.append(b"\x00" + bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")
