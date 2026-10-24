#!/usr/bin/env python3
"""Minimal cross-version smoke test for py3-pymupdf.

Deliberately uses only APIs that exist in every PyMuPDF release from 1.13 to
1.19 (the range this repository packages), so it can run unchanged in every
Alpine container of the compatibility matrix.
"""
import os
import sys

import fitz

out = os.environ.get("TEST_OUT", "/tmp/pymupdf-smoke")
os.makedirs(out, exist_ok=True)


def version(name):
    return getattr(fitz, name, "?")


print("python      : %s" % sys.version.split()[0])
print("fitz module : %s" % fitz.__file__)
print("VersionBind : %s" % version("VersionBind"))
print("VersionFitz : %s" % version("VersionFitz"))

# 1. create a PDF from scratch
doc = fitz.open()
page = doc.newPage(width=400, height=300)
page.insertText(fitz.Point(40, 80), "Hello PyMuPDF on Alpine", fontsize=20)
page.insertText(fitz.Point(40, 130), "MuPDF %s" % version("VersionFitz"), fontsize=14)
page.drawRect(fitz.Rect(30, 40, 370, 150), color=(0, 0, 1), width=2)
pdf = os.path.join(out, "hello.pdf")
doc.save(pdf)
doc.close()
print("wrote       : %s %d bytes" % (pdf, os.path.getsize(pdf)))
assert os.path.getsize(pdf) > 500, "saved pdf is suspiciously small"

# 2. reopen: text extraction + rendering
doc = fitz.open(pdf)
assert doc.pageCount == 1, doc.pageCount
text = doc[0].getText().strip()
print("text        : %r" % text)
assert "Hello PyMuPDF" in text, "text extraction failed"

pix = doc[0].getPixmap(matrix=fitz.Matrix(2, 2))
png = os.path.join(out, "hello.png")
pix.writePNG(png)
print("rendered    : %dx%d %d bytes" % (pix.width, pix.height, os.path.getsize(png)))
assert pix.width > 100 and os.path.getsize(png) > 1000, "pixmap render failed"

# 3. in-memory round trip (tobytes was added after 1.14)
data = doc.tobytes() if hasattr(doc, "tobytes") else doc.write()
assert data[:4] == b"%PDF", "not a pdf stream"
print("in-memory   : %d bytes" % len(data))
doc.close()

print("RESULT: SMOKE OK")
