#!/usr/bin/env python3
"""Derive the release matrix empirically (developer tool, needs root + chroot).

Implements the agreed procedure:

    build for Alpine N  ->  test on Alpine N  ->  test the same apk on Alpine N+1
    if N+1 passes, the apk's install scope extends; if it fails, N+1 needs a
    build of its own (usually the next PyMuPDF release line).

    sh scripts/derive_matrix.py 3.10:1.16.0 --check 3.11
    sh scripts/derive_matrix.py 3.11:1.16.9 --check 3.12 3.13

Each run leaves a JSON record in .cache/derive/, which is what gets merged
into matrix.json once a line is accepted.

The chroots are throw-away minirootfs trees under .cache/rootfs/<alpine>.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache")
# the rootfs must be reachable by the unprivileged build user, so keep it out of
# $HOME (which is 0700) - override with DERIVE_WORK
WORK = os.environ.get("DERIVE_WORK", "/var/tmp/pymupdf-derive")
MIRROR = "https://mirrors.aliyun.com/alpine"
PYPI_MIRROR = os.environ.get("PYPI_MIRROR", "https://pypi.tuna.tsinghua.edu.cn")


def log(msg):
    print(">>> %s" % msg, flush=True)


def run(cmd, **kw):
    kw.setdefault("universal_newlines", True)
    log(" ".join(cmd) if isinstance(cmd, list) else cmd)
    return subprocess.run(cmd, **kw)


def sh(cmd, check=True, capture=False):
    return subprocess.run(
        ["/bin/sh", "-c", cmd],
        check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        universal_newlines=True,
    )


# --------------------------------------------------------------------------
# chroot plumbing
# --------------------------------------------------------------------------
def rootfs_path(alpine):
    return os.path.join(WORK, "rootfs", alpine)



SINK_FILES = ("null", "zero")


def make_devices(path):
    """A minirootfs tar carries no device nodes and mknod is not available in
    unprivileged containers; writable regular files are enough for /dev/null
    and /dev/zero usage during a build."""
    dev = os.path.join(path, "dev")
    os.makedirs(dev, exist_ok=True)
    for name in SINK_FILES:
        target = os.path.join(dev, name)
        try:
            if os.path.lexists(target):
                os.remove(target)
            with open(target, "w"):
                pass
            os.chmod(target, 0o666)
        except OSError as exc:
            log("WARNING: cannot create /dev/%s (%s)" % (name, exc))


def latest_minirootfs(alpine):
    url = "%s/v%s/releases/x86_64/" % (MIRROR, alpine)
    with urllib.request.urlopen(url, timeout=60) as fh:
        html = fh.read().decode("utf-8", "replace")
    found = []
    for name in re.findall(r"alpine-minirootfs-[0-9][^\"<>]*?-x86_64\.tar\.gz", html):
        m = re.match(r"alpine-minirootfs-(\d+\.\d+\.\d+)-", name)
        if m and m.group(1).startswith(alpine + "."):
            found.append((tuple(int(x) for x in m.group(1).split(".")), name))
    if not found:
        raise SystemExit("no minirootfs found for alpine %s at %s" % (alpine, url))
    found.sort()
    return "%s%s" % (url, found[-1][1])


def ensure_rootfs(alpine):
    path = rootfs_path(alpine)
    marker = os.path.join(path, "etc", "alpine-release")
    if os.path.exists(marker):
        log("reusing rootfs %s (%s)" % (path, open(marker).read().strip()))
        make_devices(path)
        make_devices(path)
        return path

    os.makedirs(path, exist_ok=True)
    tarball = os.path.join(CACHE, "alpine-minirootfs-%s.tar.gz" % alpine)
    if not os.path.exists(tarball):
        url = latest_minirootfs(alpine)
        log("downloading %s" % url)
        urllib.request.urlretrieve(url, tarball)
    log("extracting into %s" % path)
    with tarfile.open(tarball) as tf:
        tf.extractall(path)

    shutil.copy("/etc/resolv.conf", os.path.join(path, "etc", "resolv.conf"))
    with open(os.path.join(path, "etc", "apk", "repositories"), "w") as fh:
        for repo in ("main", "community"):
            fh.write("%s/v%s/%s\n" % (MIRROR, alpine, repo))
    make_devices(path)
    # busybox `readlink -f` misbehaves in a chroot without /proc, and abuild 3.4
    # depends on it; coreutils provides a working one.
    # (always install: Alpine ships /usr/bin/readlink as a busybox symlink, so a
    # mere existence check is not enough)
    sh("chroot %s /bin/sh -c 'apk update >/dev/null 2>&1; "
       "apk add --no-cache coreutils >/dev/null 2>&1'" % path, check=False)
    return path


def copy_repo(path):
    dest = os.path.join(path, "work")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    os.makedirs(os.path.join(dest, "src"), exist_ok=True)
    sh(
        "cd %s && tar -cf - --exclude=.cache --exclude=artifacts --exclude=.git . | "
        "(cd %s && tar -xf -)" % (ROOT, dest)
    )
    return dest


def chroot(path, cmd, check=True, capture=False):
    return sh("chroot %s /bin/sh -c %s" % (path, quote(cmd)), check=check, capture=capture)


def quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


# --------------------------------------------------------------------------
# build / test
# --------------------------------------------------------------------------
# Derivation answers one question: does PyMuPDF X compile and run against the
# Python + MuPDF that Alpine N ships?  It therefore compiles the extension
# in-place (setup.py build_ext) inside a throw-away rootfs - no abuild, no
# packaging.  Releasable apks are only ever produced by build-apk.sh in CI.
def sdist_url(pymupdf):
    """Resolve the real sdist URL from the PEP 503 index (the legacy
    /packages/source/ path 404s for several releases)."""
    index = "%s/simple/pymupdf/" % PYPI_MIRROR.rstrip("/")
    with urllib.request.urlopen(index, timeout=90) as fh:
        html = fh.read().decode("utf-8", "replace")
    want = "pymupdf-%s.tar.gz" % pymupdf.lower()
    for href in re.findall(r'href="([^"]+)"', html):
        if href.split("#")[0].lower().endswith(want):
            href = href.split("#")[0]
            if href.startswith("http"):
                return href
            return urllib.parse.urljoin(index, href)
    raise SystemExit("no sdist for PyMuPDF %s in %s" % (pymupdf, index))


DEPS = ("gcc g++ musl-dev pkgconf python3 python3-dev mupdf mupdf-dev "
        "freetype-dev openjpeg-dev jbig2dec-dev libjpeg-turbo-dev zlib-dev "
        "harfbuzz-dev py3-setuptools swig curl")
# Alpine's libmupdf.so leaves these for the loading program (MuPDF >= 1.16)
LINK_LIBS = ("-Wl,--no-as-needed -lfreetype -ljpeg -lopenjp2 -ljbig2dec "
             "-lharfbuzz -lz")


def build(alpine, pymupdf, pkgrel):
    path = ensure_rootfs(alpine)
    copy_repo(path)                      # tests/ and the repo tools
    src = os.path.join(path, "build", "PyMuPDF-%s" % pymupdf)

    url = sdist_url(pymupdf)
    tarball = "PyMuPDF-%s.tar.gz" % pymupdf
    setup = (
        "set -e; mkdir -p /build; cd /build; "
        "apk add --no-cache %s >/dev/null 2>&1; "
        "curl -fsSL -m 300 -o %s %s; "
        "tar xzf %s; cd PyMuPDF-%s; "
        "if [ -e /usr/lib/libmupdf-third.so ]; then sed -i 's/\"mupdfthird\"/\"mupdf-third\"/g' setup.py || true; "
        "elif [ -e /usr/lib/libmupdfthird.so ]; then sed -i 's/\"mupdf-third\"/\"mupdfthird\"/g' setup.py || true; "
        "else sed -i 's/\"mupdf-third\",//; s/\"mupdfthird\",//' setup.py || true; fi; "
        "if grep -q jm_valid_chars fitz/fitz_wrap.c 2>/dev/null && "
        "! nm -D /usr/lib/libmupdf.so.0 2>/dev/null | grep -q jm_valid_chars; then "
        "printf '#include <mupdf/fitz.h>\\nvoid jm_valid_chars(fz_context *c, fz_font *f, void *p)"
        "{(void)c;(void)f;(void)p;}\\n' > compat_mujs_stub.c; "
        "sed -i 's|\\[\"fitz/fitz_wrap.c\"\\]|[\"fitz/fitz_wrap.c\", \"compat_mujs_stub.c\"]|' setup.py; fi; "
        'LDFLAGS="$LDFLAGS %s" CPPFLAGS="$CPPFLAGS -I/usr/include/freetype2" python3 setup.py build_ext --inplace --force'
    ) % (DEPS, tarball, url, tarball, pymupdf, LINK_LIBS)
    res = chroot(path, setup, check=False)
    ok = res.returncode == 0 and os.path.isdir(src)
    log("BUILD %s on alpine %s: %s" % (pymupdf, alpine, "OK" if ok else "FAILED"))
    return ok, src


def test_in(alpine, host_src, pymupdf, tag):
    path = ensure_rootfs(alpine)
    copy_repo(path)
    # ship the tree built for the *source* release into this rootfs (also
    # needed for the same release, where /work was just recreated)
    dest = os.path.join(path, "build")
    os.makedirs(dest, exist_ok=True)
    sh("cd %s && tar cf - %s | (cd %s && tar xf -)"
       % (os.path.dirname(host_src), os.path.basename(host_src), dest))
    src_rel = "/build/%s" % os.path.basename(host_src)
    cmd = ("cd %s && PYTHONPATH=. TEST_OUT=/tmp/t-%s python3 /work/tests/smoke.py "
           "&& PYTHONPATH=. TEST_OUT=/tmp/t-%s python3 /work/tests/feature.py"
           % (src_rel, alpine, alpine))
    res = chroot(path, cmd, check=False)
    ok = res.returncode == 0
    log("TEST %s on alpine %s: %s" % (tag, alpine, "PASS" if ok else "FAIL"))
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pairs", nargs="+", help="ALPINE:PYMUPDF, e.g. 3.10:1.16.0")
    ap.add_argument("--check", nargs="*", default=None,
                    help="Alpine releases to test the apk on (default: build release + next)")
    ap.add_argument("--pkgrel", default=os.environ.get("PKGREL", "0"),
                    help="pkgrel for the probe builds (default 0, keeps them out of releases)")
    args = ap.parse_args(argv)

    os.makedirs(os.path.join(CACHE, "derive"), exist_ok=True)
    failures = 0

    for pair in args.pairs:
        alpine, _, pymupdf = pair.partition(":")
        if not pymupdf:
            raise SystemExit("bad pair %r, expected ALPINE:PYMUPDF" % pair)

        log("=========== alpine %s / PyMuPDF %s ===========" % (alpine, pymupdf))
        built, src = build(alpine, pymupdf, args.pkgrel)
        record = {"alpine": alpine, "pymupdf": pymupdf, "built": built,
                  "installs_on": {}}
        src_rel = "/build/PyMuPDF-%s" % pymupdf

        if built:
            targets = args.check
            if targets is None:
                major, minor = alpine.split(".")
                targets = ["%s.%d" % (major, int(minor) + 1)]
            for target in targets:
                ok = test_in(target, src, pymupdf, "v" + pymupdf)
                record["installs_on"][target] = "pass" if ok else "fail"
                if not ok and target == alpine:
                    failures += 1
        else:
            failures += 1

        name = os.path.join(CACHE, "derive", "%s-%s.json" % (alpine, pymupdf))
        with open(name, "w") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
        log("record: %s" % name)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
