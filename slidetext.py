#!/usr/bin/env python3
"""Extract slide text from a .pptx (or plain text from a .pdf) into a .txt sidecar.

Stdlib only. A .pptx is a zip of XML; slide body text lives in <a:t> elements and
speaker notes in ppt/notesSlides/. Both are worth keeping: Aamodt puts the actual
explanation in the notes on several decks.

    python3 slidetext.py deck.pptx            # writes deck.txt beside it
    python3 slidetext.py deck.pptx -          # to stdout
"""
import re
import sys
import zipfile
from pathlib import Path

T = re.compile(r"<a:t>(.*?)</a:t>", re.S)
ENT = [("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")]


def _unescape(s):
    for a, b in ENT:
        s = s.replace(a, b)
    return s


def _num(name):
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


def _texts(zf, name):
    xml = zf.read(name).decode("utf-8", "replace")
    return [_unescape(t).strip() for t in T.findall(xml) if t.strip()]


def pptx_text(path):
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_num)
        # notesSlideN.xml is not guaranteed to line up with slideN.xml, so resolve
        # the real pairing through each slide's relationship file.
        notes_for = {}
        for s in slides:
            rels = f"ppt/slides/_rels/{Path(s).name}.rels"
            if rels not in names:
                continue
            rel = zf.read(rels).decode("utf-8", "replace")
            m = re.search(r'Target="\.\./(notesSlides/notesSlide\d+\.xml)"', rel)
            if m:
                notes_for[s] = "ppt/" + m.group(1)
        out = []
        for i, s in enumerate(slides, 1):
            out.append(f"=== SLIDE {i} ===")
            out.extend(_texts(zf, s))
            n = notes_for.get(s)
            if n and n in names:
                body = [t for t in _texts(zf, n) if t != str(i)]
                if body:
                    out.append("--- notes ---")
                    out.extend(body)
            out.append("")
        return "\n".join(out)


def pdf_text(path):
    import logging

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        from pypdf import PdfReader
    except ImportError:
        # Raise, don't exit: piazza.py catches this per-file so one unreadable
        # pdf does not abandon a whole ingest.
        raise RuntimeError("pdf extraction needs pypdf (pip install pypdf)")
    return "\n\n".join(
        f"=== PAGE {i} ===\n{p.extract_text() or ''}"
        for i, p in enumerate(PdfReader(str(path)).pages, 1)
    )


def extract(path):
    path = Path(path)
    return pdf_text(path) if path.suffix.lower() == ".pdf" else pptx_text(path)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    text = extract(src)
    if len(sys.argv) > 2 and sys.argv[2] == "-":
        print(text)
    else:
        dst = src.with_suffix(".txt")
        dst.write_text(text)
        print(f"{dst}  ({text.count('=== SLIDE') or text.count('=== PAGE')} slides, {len(text)} chars)")
