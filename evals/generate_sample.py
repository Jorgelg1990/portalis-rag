"""Generate the sample evaluation PDF (no third-party dependencies).

Run: python evals/generate_sample.py
Creates evals/manual-aduanas.pdf, a 2-page document used by the retrieval eval
set. Kept in the repo so the eval corpus is reproducible.
"""

import os

PAGES = [
    [
        "MANUAL OPERATIVO DE ADUANAS - PORTALIS LOGISTICA",
        "",
        "1. Documentacion requerida para la importacion",
        "Para iniciar una importacion se requieren: factura comercial, packing list,",
        "conocimiento de embarque (bill of lading), certificado de origen y",
        "declaracion aduanera de mercancias (DAM).",
        "",
        "2. Inspeccion aduanera",
        "La inspeccion aduanera se realiza en el recinto portuario. El plazo maximo",
        "es de 48 horas desde la seleccion del canal de inspeccion.",
    ],
    [
        "3. Liquidacion de tributos",
        "Los tributos se pagan dentro de los 10 dias habiles siguientes a la",
        "aceptacion de la declaracion. El impuesto general es del 16 por ciento.",
        "",
        "4. Almacenaje",
        "El almacen portuario opera de lunes a sabado de 08:00 a 20:00 horas.",
        "El periodo de almacenaje gratuito es de 5 dias.",
        "",
        "5. Canales de despacho",
        "Canal verde: despacho automatico sin revision.",
        "Canal naranja: revision documental.",
        "Canal rojo: inspeccion fisica de la mercancia.",
    ],
]


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content_stream(lines) -> bytes:
    body = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
    for line in lines:
        body.append(f"({_escape(line)}) Tj")
        body.append("T*")
    body.append("ET")
    return "\n".join(body).encode("cp1252")


def build_pdf(path: str) -> None:
    objects = {}

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(len(PAGES)))
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(PAGES)} >>".encode()
    objects[7] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"

    for index, lines in enumerate(PAGES):
        page_obj = 3 + index * 2
        content_obj = page_obj + 1
        objects[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 7 0 R >> >> /Contents {content_obj} 0 R >>"
        ).encode()
        stream = _content_stream(lines)
        objects[content_obj] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    buffer = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(buffer)
        buffer += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"

    xref_offset = len(buffer)
    max_obj = max(objects)
    buffer += f"xref\n0 {max_obj + 1}\n".encode()
    buffer += b"0000000000 65535 f \n"
    for number in range(1, max_obj + 1):
        buffer += f"{offsets[number]:010d} 00000 n \n".encode()
    buffer += (
        f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    ).encode()

    with open(path, "wb") as handle:
        handle.write(buffer)


if __name__ == "__main__":
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual-aduanas.pdf")
    build_pdf(target)
    print(f"written: {target} ({os.path.getsize(target)} bytes)")
