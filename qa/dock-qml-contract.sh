#!/usr/bin/env bash
# Render and exercise actual Xodus QML using controlled Qt6 backend objects.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
prepared=${1:?usage: dock-qml-contract.sh prepared-settings output-directory}
output=${2:?usage: dock-qml-contract.sh prepared-settings output-directory}
mkdir -p -- "$output"
output=$(cd -- "$output" && pwd)
scratch="$output/qt-build"
mkdir -p -- "$scratch/components" "$scratch/pages"
cp -- "$prepared/qml/components/"*.qml "$scratch/components/"
cp -- "$repo/overlay/identity/settings/qml/pages/AppearancePage.qml" "$scratch/pages/"
printf 'singleton Theme 1.0 Theme.qml\n' > "$scratch/components/qmldir"
moc=$(pkg-config --variable=libexecdir Qt6Core)/moc
"$moc" "$repo/qa/dock-render-acceptance.cpp" -o "$scratch/dock-render-acceptance.moc"
# pkg-config emits compiler argument words intentionally.
# shellcheck disable=SC2046
g++ -std=c++17 "$repo/qa/dock-render-acceptance.cpp" -I"$scratch" \
    -o "$scratch/dock-qt-tests" $(pkg-config --cflags --libs Qt6QuickTest Qt6Quick Qt6Qml Qt6Svg)
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
XODUS_SETTINGS_PAGE="$scratch/pages/AppearancePage.qml" \
XODUS_RENDER_DIRECTORY="$output" \
    "$scratch/dock-qt-tests" -input "$repo/qa/tst_dock_appearance.qml"
for screenshot in dock-light.png dock-dark.png settings-appearance.png; do
    test -s "$output/$screenshot"
done
