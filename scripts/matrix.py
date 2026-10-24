#!/usr/bin/env python3
"""Query the release contract (matrix.json) and render APKBUILDs.

Only the Python standard library is used so this runs inside a bare Alpine
container (no PyYAML needed).

Commands
--------
  tags                          list every tag that is allowed to release
  get --tag v1.13.20 [--field build.alpine]
  resolve --tag v1.13.20 [--json]     full entry, or exit 2 if unknown
  install-matrix --tag v1.13.20 --json  ["3.8","3.9"] for CI jobs
  render-apkbuild --tag v1.13.20 --pkgrel 20261022 --out APKBUILD
  markdown                      markdown tables used by docs/COMPATIBILITY.md
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRIX = os.path.join(ROOT, "matrix.json")
TEMPLATE = os.path.join(ROOT, "apkbuild", "APKBUILD.in")


def load():
    with open(MATRIX, encoding="utf-8") as fh:
        return json.load(fh)


def find(data, tag):
    for entry in data["releases"]:
        if entry["tag"] == tag:
            return entry
    return None


def field(entry, dotted):
    """Dotted-path lookup such as build.alpine."""
    cur = entry
    for part in dotted.split("."):
        if isinstance(cur, list):
            raise SystemExit("field %r is a list" % dotted)
        if part not in cur:
            raise SystemExit("no such field: %s" % dotted)
        cur = cur[part]
    return cur


def default_pkgrel():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")


def sha512_of(path):
    h = hashlib.sha512()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def render(entry, pkgrel, tarball=None):
    with open(TEMPLATE, encoding="utf-8") as fh:
        text = fh.read()
    build = entry["build"]
    if tarball and os.path.exists(tarball):
        sums = "%s  PyMuPDF-%s.tar.gz" % (sha512_of(tarball), entry["pymupdf"])
    else:
        sums = ""  # `abuild checksum` fills this in before building
    libs = build.get("extra_link_libs") or []
    link_ldflags = ""
    if libs:
        link_ldflags = "-Wl,--no-as-needed " + " ".join("-l" + lib for lib in libs)
    values = {
        "@PKGNAME@": "py3-pymupdf",
        "@PYMUPDF@": entry["pymupdf"],
        "@PKGREL@": str(pkgrel),
        "@ALPINE@": build["alpine"],
        "@PYTHON@": build["python"],
        "@MUPDF@": build["mupdf"],
        "@MUPDF_LINE@": entry["mupdf_line"],
        "@SHA512@": sums,
        "@LINK_LDFLAGS@": link_ldflags,
    }
    for key, val in values.items():
        text = text.replace(key, val)
    return text


def cmd_tags(data, _args):
    for entry in data["releases"]:
        print(entry["tag"])
    return 0


def cmd_get(data, args):
    entry = find(data, args.tag)
    if entry is None:
        print("tag not in matrix: %s" % args.tag, file=sys.stderr)
        return 2
    if args.field:
        val = field(entry, args.field)
        print(json.dumps(val) if isinstance(val, (list, dict)) else val)
    else:
        print(entry["pymupdf"])
    return 0


def cmd_resolve(data, args):
    entry = find(data, args.tag)
    if entry is None:
        print(
            "REFUSING: tag %s is not part of the release contract (matrix.json).\n"
            "Add it to matrix.json first, see docs/MANUAL.md." % args.tag,
            file=sys.stderr,
        )
        return 2
    if args.json:
        print(json.dumps(entry))
    else:
        print(entry["tag"], entry["pymupdf"], "alpine", entry["build"]["alpine"])
    return 0


def cmd_install_matrix(data, args):
    entry = find(data, args.tag)
    if entry is None:
        print("tag not in matrix: %s" % args.tag, file=sys.stderr)
        return 2
    print(json.dumps(entry["install"]))
    return 0


def cmd_render(data, args):
    if args.pymupdf:
        # derivation mode: render for a PyMuPDF version that is not (yet) in
        # the contract, used by scripts/derive_matrix.py.
        alpine = args.alpine
        if not alpine:
            with open("/etc/alpine-release", encoding="utf-8") as fh:
                alpine = fh.read().strip()
        entry = {
            "tag": "v" + args.pymupdf,
            "pymupdf": args.pymupdf,
            "mupdf_line": "derived",
            "build": {"alpine": alpine, "python": "", "mupdf": "",
                      "extra_link_libs": [x for x in (args.link_libs or "").split(",") if x]},
        }
    else:
        entry = find(data, args.tag)
        if entry is None:
            print("tag not in matrix: %s" % args.tag, file=sys.stderr)
            return 2
    pkgrel = args.pkgrel or default_pkgrel()
    text = render(entry, pkgrel, args.tarball)
    if args.out and args.out != "-":
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("%s  (pkgver=%s pkgrel=%s)" % (args.out, entry["pymupdf"], pkgrel))
    else:
        sys.stdout.write(text)
    return 0


def cmd_gha_output(data, args):
    """Emit KEY=VALUE lines for $GITHUB_OUTPUT."""
    entry = find(data, args.tag)
    if entry is None:
        print("tag not in matrix: %s" % args.tag, file=sys.stderr)
        return 2
    build = entry["build"]
    print("tag=%s" % entry["tag"])
    print("pymupdf=%s" % entry["pymupdf"])
    print("alpine=%s" % build["alpine"])
    print("pkgrel=%s" % (args.pkgrel or default_pkgrel()))
    print("install=%s" % json.dumps(entry["install"]))
    return 0


def cmd_release_notes(data, args):
    entry = find(data, args.tag)
    if entry is None:
        print("tag not in matrix: %s" % args.tag, file=sys.stderr)
        return 2
    build = entry["build"]
    pkgrel = args.pkgrel or default_pkgrel()
    fname = "py3-pymupdf-%s-r%s.apk" % (entry["pymupdf"], pkgrel)
    print("`%s` built from the `%s` tag." % (fname, entry["tag"]))
    print()
    print("| | |")
    print("| --- | --- |")
    print("| PyMuPDF | %s |" % entry["pymupdf"])
    print(
        "| build environment | Alpine %s, Python %s, MuPDF %s (from apk) |"
        % (build["alpine"], build["python"], build["mupdf"])
    )
    print("| installed on | `/usr/lib/python%d.%d/site-packages/fitz` |"
          % tuple(int(x) for x in build["python"].split(".")))
    print("| install scope | Alpine %s |" % ", ".join(entry["install"]))
    print("| extension ABI | %s |" % build.get("abi_tag", "?"))
    print()
    print("```sh")
    print("apk add --allow-untrusted %s" % fname)
    print("python3 -c 'import fitz; print(fitz.VersionBind, fitz.VersionFitz)'")
    print("```")
    print()
    print("Check the file against `SHA256SUMS`. The signing public key is attached:")
    print("copy it into `/etc/apk/keys/` to install without `--allow-untrusted`.")
    print()
    print("PyMuPDF is AGPL-3.0. The extension is built against the distro MuPDF apk")
    print("(`main/mupdf`); no MuPDF source is bundled in this package.")
    return 0


def cmd_plan(_data, _args):
    """Emit the GitHub Actions job matrices as KEY=VALUE lines."""
    data = load()
    builds = [
        {"tag": e["tag"], "pymupdf": e["pymupdf"], "alpine": e["build"]["alpine"]}
        for e in data["releases"]
    ]
    tests = [
        {"tag": e["tag"], "alpine": alpine}
        for e in data["releases"]
        for alpine in e["install"]
    ]
    print("matrix=%s" % json.dumps({"include": builds}))
    print("tests=%s" % json.dumps({"include": tests}))
    return 0


def cmd_markdown(data, _args):
    print("<!-- generated by `scripts/matrix.py markdown`; do not edit -->\n")
    print("| tag | PyMuPDF | 编译环境 (Alpine / Python / MuPDF) | 可安装 Alpine | 状态 |")
    print("| --- | --- | --- | --- | --- |")
    for entry in data["releases"]:
        b = entry["build"]
        verified = entry.get("verified", {})
        if verified.get("released"):
            state = "已发布并验证"
        elif verified.get("built"):
            state = "已构建并验证"
        else:
            state = "已约定"
        print(
            "| `%s` | %s | %s / %s / %s | %s | %s |"
            % (
                entry["tag"],
                entry["pymupdf"],
                b["alpine"],
                b["python"],
                b["mupdf"],
                ", ".join(entry["install"]),
                state,
            )
        )
    if data.get("pending"):
        print("\n待推导（尚未进入约定）：\n")
        print("| Alpine | Python | MuPDF | 候选 PyMuPDF | 状态 |")
        print("| --- | --- | --- | --- | --- |")
        for item in data["pending"]:
            print(
                "| %s | %s | %s | %s | %s |"
                % (
                    item["alpine"],
                    item["python"],
                    item["mupdf"],
                    ", ".join(item.get("candidate_pymupdf", [])) or "-",
                    item.get("status", "-"),
                )
            )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # python 3.6 (Alpine 3.8) has no `required=` for subparsers
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("tags").set_defaults(func=cmd_tags)
    sub.add_parser("markdown").set_defaults(func=cmd_markdown)
    sub.add_parser("plan").set_defaults(func=cmd_plan)

    p = sub.add_parser("get")
    p.add_argument("--tag", required=True)
    p.add_argument("--field")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("resolve")
    p.add_argument("--tag", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("install-matrix")
    p.add_argument("--tag", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_install_matrix)

    p = sub.add_parser("gha-output")
    p.add_argument("--tag", required=True)
    p.add_argument("--pkgrel")
    p.set_defaults(func=cmd_gha_output)

    p = sub.add_parser("release-notes")
    p.add_argument("--tag", required=True)
    p.add_argument("--pkgrel")
    p.set_defaults(func=cmd_release_notes)

    p = sub.add_parser("render-apkbuild")
    p.add_argument("--tag", help="tag from matrix.json")
    p.add_argument("--pymupdf", help="derivation mode: version not in the contract")
    p.add_argument("--alpine", help="derivation mode: alpine release to stamp")
    p.add_argument("--link-libs", help="comma separated, derivation mode")
    p.add_argument("--pkgrel")
    p.add_argument("--tarball")
    p.add_argument("--out")
    p.set_defaults(func=cmd_render)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(load(), args)


if __name__ == "__main__":
    sys.exit(main())
