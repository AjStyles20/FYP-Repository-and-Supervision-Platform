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
