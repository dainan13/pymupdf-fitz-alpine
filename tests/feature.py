#!/usr/bin/env python3
"""Broader, version-adaptive API test for py3-pymupdf (1.13 ... 1.19).

The PyMuPDF API was renamed between release lines, so every optional part
probes for the callable it needs and reports SKIP instead of failing.  The
parts that must work everywhere are asserted hard.
"""
import os
import sys

import fitz

out = os.environ.get("TEST_OUT", "/tmp/pymupdf-feature")
os.makedirs(out, exist_ok=True)
skipped = []


def call(obj, *names, **kwargs):
    """Call the first existing method among *names*."""
    for name in names:
        fn = getattr(obj, name, None)
        if callable(fn):
            return fn(**kwargs)
    raise AttributeError("%r has none of %s" % (obj, names))


def opt(label, fn):
    try:
        return fn()
    except Exception as exc:                       # noqa: BLE001 - report and continue
        skipped.append("%s: %s" % (label, exc))
        print("skip        : %s (%s)" % (label, exc))
        return None


print("versions    : bind=%s fitz=%s" % (getattr(fitz, "VersionBind", "?"),
                                        getattr(fitz, "VersionFitz", "?")))

doc = fitz.open()

# --- page 1: text, vector art, embedded raster ----------------------------
p1 = doc.newPage(width=595, height=842)
p1.insertText(fitz.Point(56, 90), "PyMuPDF feature check", fontsize=24,
              fontname="Helvetica")
p1.insertTextbox(fitz.Rect(56, 110, 540, 260),
                 "The quick brown fox jumps over the lazy dog. " * 6,
                 fontsize=11, fontname="Times-Roman")
p1.drawRect(fitz.Rect(50, 80, 545, 270), color=(1, 0, 0), width=1.5)
p1.drawCircle(fitz.Point(300, 400), 60, color=(0, 0.6, 0), fill=(0.9, 1, 0.9))
shot = p1.getPixmap(matrix=fitz.Matrix(0.5, 0.5))
p1.insertImage(fitz.Rect(60, 520, 60 + shot.width, 520 + shot.height), pixmap=shot)
print("page1 image : %dx%d embedded" % (shot.width, shot.height))

# --- page 2: bezier, link, annotation ------------------------------------
p2 = doc.newPage()
p2.drawBezier(fitz.Point(50, 700), fitz.Point(150, 600),
              fitz.Point(300, 800), fitz.Point(400, 650), width=3)
p2.insertText(fitz.Point(60, 120), "highlighted text on page two", fontsize=12,
              fontname="Helvetica")
p2.addHighlightAnnot(fitz.Rect(55, 100, 300, 128))
p2.insertLink({"kind": fitz.LINK_GOTO, "from": fitz.Rect(50, 50, 200, 80),
               "page": 0, "to": fitz.Point(0, 0)})
call(doc, "setToC", "setTOC", toc=[[1, "First", 1], [1, "Second", 2]])

pdf = os.path.join(out, "feature.pdf")
doc.save(pdf, garbage=3, deflate=True)
doc.close()
print("saved       : %s %d bytes" % (pdf, os.path.getsize(pdf)))

# --- read back -----------------------------------------------------------
d = fitz.open(pdf)
assert d.pageCount == 2, d.pageCount
assert d.isPDF
toc = call(d, "getToC", "getTOC")
print("toc         : %s" % (toc,))

t1 = d[0].getText().strip()
assert "PyMuPDF feature check" in t1, t1[:80]
assert "quick brown fox" in t1
print("text p1     : %d chars" % len(t1))

blocks = d[0].getText("dict")["blocks"]
assert blocks
print("dict blocks : %d" % len(blocks))

imgs = call(d[0], "getImages", "getImageList")
assert imgs, "embedded image not found"
print("images p1   : %d" % len(imgs))

links = d[1].getLinks()
assert len(links) == 1 and links[0]["kind"] == fitz.LINK_GOTO, links
print("link p2     : kind=%d" % links[0]["kind"])

opt("annotation readback", lambda: d[1].firstAnnot and True)

# --- rendering ------------------------------------------------------------
for i in range(d.pageCount):
    pm = d[i].getPixmap(matrix=fitz.Matrix(1.5, 1.5))
    assert pm.samples
    print("render p%d   : %dx%d %d comp" % (i + 1, pm.width, pm.height, pm.n))

alpha = d[0].getPixmap(matrix=fitz.Matrix(1, 1), alpha=True)
png = os.path.join(out, "page1-alpha.png")
alpha.writePNG(png)
assert os.path.getsize(png) > 1000
print("alpha png   : %d comp %d bytes" % (alpha.n, os.path.getsize(png)))

# --- in-memory round trip -------------------------------------------------
data = call(d, "tobytes", "write", garbage=3)
assert data[:4] == b"%PDF"
print("in-memory   : %d bytes" % len(data))
mem = fitz.open(stream=data, filetype="pdf")
assert mem.pageCount == 2
mem.close()
d.close()

# --- page copy / font list ------------------------------------------------
src = fitz.open(pdf)
new = fitz.open()
new.insertPDF(src, from_page=0, to_page=0)
assert new.pageCount == 1 and "PyMuPDF" in new[0].getText()
print("insertPDF   : ok")
new.close()

fonts = opt("font list", lambda: src[0].getFontList())
if fonts is not None:
    print("fonts p1    : %s" % (fonts,))
src.close()

if skipped:
    print("skipped     : %d (%s)" % (len(skipped), "; ".join(skipped)))
print("RESULT: FEATURE OK")
