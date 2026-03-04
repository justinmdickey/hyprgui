# Maintainer: hyprgui contributors
pkgname=hyprgui-git
pkgver=0.1.0.r7.ef9f0d2
pkgrel=1
pkgdesc='GTK4 + libadwaita settings app for Hyprland'
arch=('any')
license=('MIT')
depends=('python' 'python-gobject' 'gtk4' 'libadwaita')
optdepends=('hyprland: required for Hyprland settings')
makedepends=('git')
source=("${pkgname}::git+file://${PWD}"
        'com.github.hyprgui.desktop')
sha256sums=('SKIP'
            'SKIP')

pkgver() {
  cd "$pkgname"
  printf '0.1.0.r%s.%s' "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

package() {
  cd "$pkgname"

  # Install Python package to site-packages
  local site=$(python -c "import site; print(site.getsitepackages()[0])")
  install -dm755 "$pkgdir/$site"
  cp -r hyprgui "$pkgdir/$site/hyprgui"

  # Launcher script
  install -Dm755 /dev/stdin "$pkgdir/usr/bin/hyprgui" <<'SCRIPT'
#!/bin/sh
exec python -m hyprgui "$@"
SCRIPT

  # Desktop file
  install -Dm644 "$srcdir/com.github.hyprgui.desktop" "$pkgdir/usr/share/applications/com.github.hyprgui.desktop"
}
