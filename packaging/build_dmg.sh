#!/bin/sh
# Wrap dist/OVITO-Tachyon.app into a drag-to-Applications disk image.
set -eu
VERSION="$1"
STAGE="$(mktemp -d)"
cp -R dist/OVITO-Tachyon.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
mkdir -p release
hdiutil create -volname "OVITO-Tachyon" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov \
  "release/OVITO-Tachyon-${VERSION}-macOS-arm64.dmg"
rm -rf "$STAGE"
