#!/bin/sh
# Build the py3-pymupdf apk for the Alpine release named by the release
# contract (matrix.json).
#
# Runs *inside* the target Alpine (CI container, derivation chroot or a real
# machine) as root, from the repository root:
#
#   TAG=v1.13.20 sh scripts/build-apk.sh
#
# Derivation mode (used by scripts/derive_matrix.py, never by CI):
#
#   ALLOW_UNLISTED=1 PYMUPDF=1.16.0 sh scripts/build-apk.sh
#
# Environment:
#   TAG             git tag, must exist in matrix.json          (required unless deriving)
#   PYMUPDF         PyMuPDF version (derivation mode only)
#   ALLOW_UNLISTED  set to 1 to bypass the matrix gate
#   PKGREL          apk release number, default: UTC date YYYYMMDD
#   OUT             output directory, default: $REPO/artifacts
#   DISTFILE        pre-downloaded PyMuPDF-<ver>.tar.gz         (optional)
#   PYMUPDF_MIRROR  fallback download mirror base               (optional)
#   ABUILD_PRIVKEY  base64 of the RSA private key to sign with  (optional)
#   ABUILD_PUBKEY   base64 of the matching .pub file            (optional)
#   ABUILD_PACKAGER PACKAGER string written into the package    (optional)
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
PKGREL=${PKGREL:-$(date -u +%Y%m%d)}
OUT=${OUT:-$REPO/artifacts}
APORT=/home/builder/aports/testing/py3-pymupdf

log() { printf '>>> %s\n' "$*"; }
die() { printf '>>> ERROR: %s\n' "$*" >&2; exit 1; }

[ -f /etc/alpine-release ] || die "not running on Alpine"
[ -f "$REPO/matrix.json" ] || die "matrix.json not found in $REPO"
HAVE_ALPINE=$(cat /etc/alpine-release)

# a bare minirootfs has no python3, and matrix.py needs it
if ! command -v python3 >/dev/null 2>&1; then
	log "bootstrapping python3"
	apk add --no-cache python3 >/dev/null
fi
DERIVING=0

# --- 1. release contract gate -------------------------------------------
if [ "${ALLOW_UNLISTED:-0}" = "1" ] && [ -n "${PYMUPDF:-}" ]; then
	DERIVING=1
	TAG=${TAG:-v$PYMUPDF}
	MUPDF_LINE=derived
	log "DERIVATION MODE: PyMuPDF $PYMUPDF is not part of the release contract"
else
	[ -n "${TAG:-}" ] || die "set TAG (e.g. TAG=v1.13.20)"
	WANT_ALPINE=$(python3 "$REPO/scripts/matrix.py" get --tag "$TAG" --field build.alpine) || {
		log "tag $TAG is not in matrix.json - refusing to build"
		exit 2
	}
	case "$HAVE_ALPINE" in
	"$WANT_ALPINE" | "$WANT_ALPINE".*) ;;
	*) die "tag $TAG must be built on Alpine $WANT_ALPINE, this is $HAVE_ALPINE" ;;
	esac
	PYMUPDF=$(python3 "$REPO/scripts/matrix.py" get --tag "$TAG" --field pymupdf)
	MUPDF_LINE=$(python3 "$REPO/scripts/matrix.py" get --tag "$TAG" --field mupdf_line)
fi

PY=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
log "tag=$TAG pymupdf=$PYMUPDF alpine=$HAVE_ALPINE python=$PY pkgrel=$PKGREL"

# --- 2. build dependencies, all from the distro repo --------------------
log "installing build dependencies from apk"
apk add --no-cache build-base swig pkgconf python3 python3-dev py3-setuptools \
	mupdf mupdf-dev harfbuzz-dev freetype-dev openjpeg-dev jbig2dec-dev \
	libjpeg-turbo-dev zlib-dev abuild fakeroot curl git >/dev/null

MUPDF_PKG=$(awk -F: '/^P:mupdf$/{f=1} f&&/^V:/{print $2; exit}' /lib/apk/db/installed)
log "distro mupdf: $MUPDF_PKG | python: $(python3 -V 2>&1)"

# --- 3. build user (abuild refuses to run as root) ----------------------
if ! id builder >/dev/null 2>&1; then
	adduser -D -s /bin/ash builder
	addgroup builder abuild
fi

mkdir -p /home/builder/.abuild "$OUT"
chown builder:builder /home/builder/.abuild
if [ -n "${ABUILD_PRIVKEY:-}" ]; then
	log "using the signing key from ABUILD_PRIVKEY"
	printf '%s' "$ABUILD_PRIVKEY" | base64 -d > /home/builder/.abuild/ci.rsa
	[ -n "${ABUILD_PUBKEY:-}" ] && printf '%s' "$ABUILD_PUBKEY" | base64 -d > /home/builder/.abuild/ci.rsa.pub
	chmod 600 /home/builder/.abuild/ci.rsa
	[ -f /home/builder/.abuild/ci.rsa.pub ] && chmod 644 /home/builder/.abuild/ci.rsa.pub
	chown builder:builder /home/builder/.abuild/ci.rsa 2>/dev/null || true
	chown builder:builder /home/builder/.abuild/ci.rsa.pub 2>/dev/null || true
else
	if ! ls /home/builder/.abuild/*.rsa >/dev/null 2>&1; then
		log "generating a throw-away signing key (set ABUILD_PRIVKEY to keep one)"
		su builder -s /bin/sh -c 'abuild-keygen -a -n -q' >/dev/null
	fi
fi
for k in /home/builder/.abuild/*.rsa.pub; do
	[ -f "$k" ] && cp "$k" /etc/apk/keys/
done
if [ -n "${ABUILD_PACKAGER:-}" ]; then
	printf 'PACKAGER="%s"\n' "$ABUILD_PACKAGER" > /home/builder/.abuild/packager.conf
fi

# --- 4. source tarball --------------------------------------------------
TARBALL=PyMuPDF-$PYMUPDF.tar.gz
mkdir -p /var/cache/distfiles
if [ -n "${DISTFILE:-}" ] && [ -f "$DISTFILE" ]; then
	log "using distfile $DISTFILE"
	SRC=$(readlink -f "$DISTFILE")
	DST=$(readlink -f "/var/cache/distfiles/$TARBALL" 2>/dev/null || echo "/var/cache/distfiles/$TARBALL")
	[ "$SRC" = "$DST" ] || cp "$SRC" "$DST"
elif [ ! -f /var/cache/distfiles/$TARBALL ]; then
	log "downloading $TARBALL"
	MIRROR_BASE=${PYMUPDF_MIRROR:-https://pypi.tuna.tsinghua.edu.cn/packages/source/P/PyMuPDF}
	curl -fsSL -m 300 -o /var/cache/distfiles/$TARBALL \
		"https://files.pythonhosted.org/packages/source/P/PyMuPDF/$TARBALL" ||
		curl -fsSL -m 300 -o /var/cache/distfiles/$TARBALL "$MIRROR_BASE/$TARBALL" ||
		die "cannot download $TARBALL"
fi
chmod 644 /var/cache/distfiles/$TARBALL

# --- 5. aport -----------------------------------------------------------
log "rendering APKBUILD into $APORT"
mkdir -p "$APORT"
if [ "$DERIVING" = "1" ]; then
	python3 "$REPO/scripts/matrix.py" render-apkbuild --pymupdf "$PYMUPDF" \
		--alpine "$HAVE_ALPINE" --pkgrel "$PKGREL" \
		--tarball "/var/cache/distfiles/$TARBALL" --out "$APORT/APKBUILD" >/dev/null
else
	python3 "$REPO/scripts/matrix.py" render-apkbuild --tag "$TAG" --pkgrel "$PKGREL" \
		--tarball "/var/cache/distfiles/$TARBALL" --out "$APORT/APKBUILD" >/dev/null
fi
chmod 644 "$APORT/APKBUILD"
chown -R builder:builder /home/builder/aports

# --- 6. build -----------------------------------------------------------
log "running abuild as user 'builder'"
su builder -s /bin/sh -c "cd '$APORT' && abuild"

APK=/home/builder/packages/testing/x86_64/py3-pymupdf-$PYMUPDF-r$PKGREL.apk
[ -f "$APK" ] || die "package not produced: $APK"

cp "$APK" "$OUT/"
cp /home/builder/packages/testing/x86_64/APKINDEX.tar.gz "$OUT/" 2>/dev/null || true
cp /home/builder/.abuild/*.rsa.pub "$OUT/" 2>/dev/null || true
cp "$APORT/APKBUILD" "$OUT/APKBUILD-$PYMUPDF-r$PKGREL" 2>/dev/null || true

log "artifact: $OUT/$(basename "$APK")"
sha256sum "$OUT/$(basename "$APK")" || true
if [ "$MUPDF_LINE" != "derived" ]; then
	log "install scope: $(python3 "$REPO/scripts/matrix.py" get --tag "$TAG" --field install)"
fi
