"""One-shot PDF builder for the synthetic positive-case fixture.

Run once: `.venv/bin/python tests/fixtures/synthetic_disposed_with_directions/build.py`.
The output `judgment.pdf` is checked into the fixture directory and is what
the integration test reads.

This script writes a minimal PDF 1.4 document by hand because reportlab and
ghostscript are not in the §8 dependency set (and §5.3 forbids adding new
ones for prototype). The PDF uses Times-Roman, Letter page size, fixed line
height. pdfplumber reads it cleanly; that is the only requirement.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

HERE = Path(__file__).parent
TXT_PATH = HERE / "judgment.txt"
PDF_PATH = HERE / "judgment.pdf"

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT_MARGIN = 72
TOP_MARGIN = 72
BOTTOM_MARGIN = 72
LINE_HEIGHT = 14
FONT_SIZE = 11
WRAP_WIDTH = 78


def _escape_pdf_string(s: str) -> str:
    """Escape parens and backslash. Replace non-Latin-1 with '?'."""
    out = []
    for ch in s:
        if ch == "(":
            out.append("\\(")
        elif ch == ")":
            out.append("\\)")
        elif ch == "\\":
            out.append("\\\\")
        elif ord(ch) < 32 or ord(ch) > 126:
            out.append("?")
        else:
            out.append(ch)
    return "".join(out)


def _wrap_lines(raw: str) -> list[str]:
    out: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            out.append("")
            continue
        wrapped = textwrap.wrap(
            line,
            width=WRAP_WIDTH,
            break_long_words=False,
            break_on_hyphens=False,
        )
        if not wrapped:
            out.append("")
        else:
            out.extend(wrapped)
    return out


def _pages(lines: list[str]) -> list[list[str]]:
    available = PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN
    lines_per_page = max(1, available // LINE_HEIGHT)
    pages: list[list[str]] = []
    for i in range(0, len(lines), lines_per_page):
        pages.append(lines[i : i + lines_per_page])
    return pages


def _content_stream(page_lines: list[str]) -> bytes:
    parts: list[str] = ["BT", f"/F1 {FONT_SIZE} Tf"]
    parts.append(f"{LEFT_MARGIN} {PAGE_HEIGHT - TOP_MARGIN} Td")
    first = True
    for line in page_lines:
        escaped = _escape_pdf_string(line)
        if first:
            parts.append(f"({escaped}) Tj")
            first = False
        else:
            parts.append(f"0 -{LINE_HEIGHT} Td ({escaped}) Tj")
    parts.append("ET")
    return ("\n".join(parts) + "\n").encode("latin-1")


def build_pdf() -> bytes:
    raw = TXT_PATH.read_text(encoding="utf-8")
    lines = _wrap_lines(raw)
    pages = _pages(lines)

    n_pages = len(pages)
    # Object numbering:
    #   1 Catalog
    #   2 Pages
    #   3 Font
    #   4..(3+n) Page objects
    #   (4+n)..(3+2n) Content streams
    n_objects = 3 + 2 * n_pages
    page_obj_start = 4
    content_obj_start = 4 + n_pages

    out = bytearray()
    offsets: dict[int, int] = {}

    out.extend(b"%PDF-1.4\n")
    out.extend(b"%\xe2\xe3\xcf\xd3\n")  # binary marker per PDF spec hint

    # Object 1: Catalog
    offsets[1] = len(out)
    out.extend(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    # Object 2: Pages
    offsets[2] = len(out)
    kids = " ".join(f"{page_obj_start + i} 0 R" for i in range(n_pages))
    out.extend(
        f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>\nendobj\n".encode(
            "latin-1"
        )
    )

    # Object 3: Font
    offsets[3] = len(out)
    out.extend(
        b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman "
        b"/Encoding /WinAnsiEncoding >>\nendobj\n"
    )

    # Page objects
    for i in range(n_pages):
        obj_num = page_obj_start + i
        content_num = content_obj_start + i
        offsets[obj_num] = len(out)
        out.extend(
            (
                f"{obj_num} 0 obj\n<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_num} 0 R >>\nendobj\n"
            ).encode("latin-1")
        )

    # Content streams
    for i, page_lines in enumerate(pages):
        obj_num = content_obj_start + i
        offsets[obj_num] = len(out)
        body = _content_stream(page_lines)
        out.extend(
            f"{obj_num} 0 obj\n<< /Length {len(body)} >>\nstream\n".encode(
                "latin-1"
            )
        )
        out.extend(body)
        out.extend(b"\nendstream\nendobj\n")

    # xref
    xref_offset = len(out)
    out.extend(f"xref\n0 {n_objects + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for i in range(1, n_objects + 1):
        out.extend(f"{offsets[i]:010d} 00000 n \n".encode("latin-1"))

    # trailer
    out.extend(
        f"trailer\n<< /Size {n_objects + 1} /Root 1 0 R >>\nstartxref\n"
        f"{xref_offset}\n%%EOF\n".encode("latin-1")
    )

    return bytes(out)


def main() -> None:
    PDF_PATH.write_bytes(build_pdf())
    print(f"wrote {PDF_PATH} ({PDF_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
