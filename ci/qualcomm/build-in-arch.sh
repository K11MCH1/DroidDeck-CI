#!/usr/bin/bash
# Builds DroidDeck's private Qualcomm Gamescope, Zink and WSI layer with the recipes in tools/qualcomm.
# Runs as root inside menci/archlinuxarm:base-devel, with the DroidDeck checkout at /work and this
# repository's ci/ directory at /ci. Results are copied to /work/qualcomm-out.
set -euxo pipefail
cd /work

grep -q '^DisableSandbox' /etc/pacman.conf || sed -i 's/^\[options\]/[options]\nDisableSandbox/' /etc/pacman.conf
{ for m in https://ca.us.mirror.archlinuxarm.org https://fl.us.mirror.archlinuxarm.org https://de3.mirror.archlinuxarm.org https://nl.mirror.archlinuxarm.org; do echo "Server = $m/\$arch/\$repo"; done; cat /etc/pacman.d/mirrorlist; } > /etc/pacman.d/mirrorlist.new
mv /etc/pacman.d/mirrorlist.new /etc/pacman.d/mirrorlist
# The phone build root linked exactly these libraries (ci/qualcomm/expected-needed.txt); libunwind and
# valgrind stay uninstalled so Mesa does not pick them up as extra dependencies.
packages=(
  git python python-mako python-packaging python-yaml meson ninja cmake pkgconf flex bison zstd
  glslang spirv-tools spirv-headers vulkan-headers vulkan-icd-loader
  wayland wayland-protocols libdrm libglvnd xorgproto libx11 libxcb libxext libxfixes libxdamage
  libxcomposite libxrender libxres libxtst libxxf86vm libxshmfence libxrandr libxmu libxi libxcursor
  libxkbcommon xcb-util-wm xcb-util-errors xcb-util-renderutil pixman lcms2 systemd-libs seatd libinput
  libcap libdisplay-info hwdata libdecor luajit glm sdl2-compat xorg-xwayland expat zlib lm_sensors
)
pacman -Sy --noconfirm
available=()
for package in "${packages[@]}"; do
  if pacman -Si "$package" >/dev/null 2>&1; then available+=("$package"); else echo "::warning::Arch Linux ARM has no package $package"; fi
done
pacman -Su --noconfirm --needed "${available[@]}"
git config --global --add safe.directory '*'

jobs=$(nproc)
{
  echo "gcc: $(gcc -dumpfullversion) ($(gcc --version | head -1))"
  echo "glibc: $(ldd --version | head -1)"
  echo "meson: $(meson --version)"
  echo "image: menci/archlinuxarm:base-devel, packages updated $(date -u +%Y-%m-%dT%H:%MZ)"
} > qualcomm-toolchain.txt
cat qualcomm-toolchain.txt

python3 -I - <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, 'tools/qualcomm')
import fetch_runtime
lock = json.loads(Path('tools/qualcomm/runtime.json').read_text())
print(fetch_runtime.fetch(Path('build/qualcomm-cache'), lock['wsi']))
EOF

rm -rf build/qualcomm-gamescope/source build/qualcomm-zink/source build/qualcomm-wsi/source
python3 tools/qualcomm/build_gamescope.py --jobs "$jobs"
python3 tools/qualcomm/build_zink.py --jobs "$jobs"
python3 tools/qualcomm/build_wsi.py --jobs "$jobs"

out=qualcomm-out
rm -rf "$out" && mkdir -p "$out/qualcomm-gamescope" "$out/qualcomm-zink" "$out/qualcomm-wsi"
cp build/qualcomm-gamescope/gamescope build/qualcomm-gamescope/source.tar.gz build/qualcomm-gamescope/build.json "$out/qualcomm-gamescope/"
cp -r build/qualcomm-zink/runtime "$out/qualcomm-zink/runtime"
find build/qualcomm-wsi -maxdepth 1 -type f -exec cp {} "$out/qualcomm-wsi/" \;
cp qualcomm-toolchain.txt "$out/"

python3 -I /ci/qualcomm/check_needed.py "$out" tools/gamescope/runtime-sonames.txt /ci/qualcomm/expected-needed.txt | tee "$out/needed.md"
