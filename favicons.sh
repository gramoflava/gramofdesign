#!/bin/sh
# favicons.sh — build a site's favicon set from its gramof mark.
#
#   ./favicons.sh marks/<site>.svg <site-root> [--manifest]
#
# Writes into <site-root>:
#   favicon.svg            the mark, verbatim (what modern browsers use)
#   favicon.ico            32×32, for legacy clients and the implicit /favicon.ico request
#   apple-touch-icon.png   180×180, opaque, full-bleed square (iOS/Safari rounds it itself)
#   android-chrome-{192x192,512x512}.png   only with --manifest
#
# Needs rsvg-convert and ImageMagick (brew install librsvg imagemagick).
set -eu

[ $# -ge 2 ] || { echo "usage: $0 <mark.svg> <site-root> [--manifest]" >&2; exit 2; }
mark=$1 out=$2 manifest=${3:-}
[ -f "$mark" ] || { echo "no such mark: $mark" >&2; exit 1; }
[ -d "$out" ] || { echo "no such directory: $out" >&2; exit 1; }

command -v rsvg-convert >/dev/null || { echo "rsvg-convert not found (brew install librsvg)" >&2; exit 1; }
if command -v magick >/dev/null; then im=magick; else im=convert; fi
command -v "$im" >/dev/null || { echo "ImageMagick not found (brew install imagemagick)" >&2; exit 1; }

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

# 1. SVG: the mark itself.
cp "$mark" "$out/favicon.svg"

# 2. ICO: a single 32 px frame, transparent rounded corners like the SVG.
rsvg-convert -w 32 -h 32 "$mark" -o "$tmp/32.png"
"$im" "$tmp/32.png" "$out/favicon.ico"

# 3. Touch icon: drop the squircle radius so the background fills the square,
#    then flatten onto white (covers marks without a background, e.g. glassbox).
perl -0pe 's/(<rect width="32" height="32") rx="[^"]*"/$1/' "$mark" > "$tmp/square.svg"
rsvg-convert -w 180 -h 180 "$tmp/square.svg" -o "$tmp/180.png"
"$im" "$tmp/180.png" -background white -flatten -alpha off -strip "$out/apple-touch-icon.png"

# 4. Manifest icons, only for installable sites.
if [ "$manifest" = "--manifest" ]; then
  for s in 192 512; do
    rsvg-convert -w $s -h $s "$mark" -o "$tmp/$s.png"
    "$im" "$tmp/$s.png" -strip "$out/android-chrome-${s}x${s}.png"
  done
fi

echo "favicons for $(basename "$mark" .svg) → $out"
echo "next: ./check.py --sync"
