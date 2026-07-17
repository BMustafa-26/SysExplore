#!/usr/bin/env bash
# SysDev Explorer - kurulum / kaldırma betiği
#
# Kullanım:
#   ./install.sh install     Uygulamayı kurar
#   ./install.sh uninstall   Uygulamayı kaldırır
#   ./install.sh status      Kurulum durumunu gösterir
#   ./install.sh             İnteraktif menü açar
#
# Seçenekler: -y/--yes (sorulara otomatik evet), --no-deps (sistem paketlerini
# atla), --purge (uninstall ile birlikte ~/.config/sysdev-explorer'ı da siler)
set -euo pipefail

APP_NAME="sysdev-explorer"
APP_DISPLAY_NAME="SysDev Explorer"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

INSTALL_DIR="${SYSDEV_EXPLORER_INSTALL_DIR:-$HOME/.local/share/$APP_NAME}"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
CONFIG_DIR="$HOME/.config/$APP_NAME"

LAUNCHER_PATH="$BIN_DIR/$APP_NAME"
DESKTOP_FILE="$DESKTOP_DIR/$APP_NAME.desktop"
ICON_FILE="$ICON_DIR/$APP_NAME.svg"

ASSUME_YES=0
SKIP_DEPS=0
PURGE=0

# -- yardımcılar -------------------------------------------------------------
color() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
info()  { echo "$(color '1;35' '[SysDev Explorer]') $1"; }
ok()    { echo "$(color '1;32' '✓') $1"; }
warn()  { echo "$(color '1;33' '!') $1"; }
err()   { echo "$(color '1;31' '✗') $1" >&2; }

usage() {
  cat <<EOF
$APP_DISPLAY_NAME kurulum betiği

Kullanım: $0 [install|uninstall|status] [seçenekler]

Komutlar:
  install       $APP_DISPLAY_NAME kurar (varsayılan)
  uninstall     $APP_DISPLAY_NAME kaldırır
  status        Kurulum durumunu gösterir

Seçenekler:
  -y, --yes     Tüm sorulara otomatik "evet" cevabı verir
  --no-deps     Sistem bağımlılıklarını (GTK3/VTE) kurmayı atlar
  --purge       (uninstall) ~/.config/$APP_NAME yapılandırmasını da siler
  -h, --help    Bu yardım metnini gösterir
EOF
}

confirm() {
  local prompt="$1"
  if [ "$ASSUME_YES" -eq 1 ]; then
    return 0
  fi
  read -r -p "$prompt [E/h] " reply
  case "$reply" in
    [hH]*) return 1 ;;
    *) return 0 ;;
  esac
}

# -- bağımlılıklar ------------------------------------------------------------
detect_pkg_manager() {
  if command -v apt-get >/dev/null 2>&1; then echo apt
  elif command -v dnf >/dev/null 2>&1; then echo dnf
  elif command -v pacman >/dev/null 2>&1; then echo pacman
  elif command -v zypper >/dev/null 2>&1; then echo zypper
  elif command -v apk >/dev/null 2>&1; then echo apk
  else echo unknown
  fi
}

check_gtk_available() {
  python3 - <<'PY' >/dev/null 2>&1
import sys
try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # noqa: F401
except Exception:
    sys.exit(1)
PY
}

check_vte_available() {
  python3 - <<'PY' >/dev/null 2>&1
import sys
try:
    import gi
    gi.require_version("Vte", "2.91")
    from gi.repository import Vte  # noqa: F401
except Exception:
    sys.exit(1)
PY
}

# Some systems have several python3 interpreters on PATH (pyenv, conda, distro
# multi-version installs) whose compiled gi bindings don't match "python3".
# Pick the first interpreter that can actually import Gtk 3.0 so the launcher
# doesn't silently point at a broken one.
resolve_python_bin() {
  local candidate
  for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: F401
PY
    then
      echo "$candidate"
      return 0
    fi
  done
  echo "python3"
}

install_dependencies() {
  if [ "$SKIP_DEPS" -eq 1 ]; then
    warn "Bağımlılık kurulumu atlandı (--no-deps)"
    return 0
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    err "python3 bulunamadı. Lütfen önce Python 3 kurun."
    exit 1
  fi

  local need_gtk=0 need_vte=0
  check_gtk_available || need_gtk=1
  check_vte_available || need_vte=1

  if [ "$need_gtk" -eq 0 ] && [ "$need_vte" -eq 0 ]; then
    ok "Gerekli GTK3/VTE bileşenleri zaten kurulu"
    return 0
  fi

  local pm
  pm="$(detect_pkg_manager)"
  if [ "$pm" = "unknown" ]; then
    warn "Paket yöneticisi tespit edilemedi."
    warn "Lütfen PyGObject + GTK3 (ve isteğe bağlı VTE terminal kitaplığını) elle kurun."
    return 0
  fi

  local sudo_cmd=""
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
      sudo_cmd="sudo"
    else
      warn "sudo bulunamadı; sistem paketleri otomatik kurulamıyor. Elle kurmanız gerekebilir."
      return 0
    fi
  fi

  if ! confirm "Eksik sistem bağımlılıkları ($pm ile) kurulsun mu?"; then
    warn "Bağımlılık kurulumu atlandı."
    return 0
  fi

  info "Sistem bağımlılıkları kuruluyor ($pm)..."
  case "$pm" in
    apt)
      $sudo_cmd apt-get update
      $sudo_cmd apt-get install -y python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0
      $sudo_cmd apt-get install -y gir1.2-vte-2.91 || warn "VTE paketi kurulamadı; gömülü terminal yerine sistem terminali kullanılacak."
      ;;
    dnf)
      $sudo_cmd dnf install -y python3 python3-gobject gtk3
      $sudo_cmd dnf install -y vte291 || warn "VTE paketi kurulamadı; gömülü terminal yerine sistem terminali kullanılacak."
      ;;
    pacman)
      $sudo_cmd pacman -S --needed --noconfirm python python-gobject gtk3
      $sudo_cmd pacman -S --needed --noconfirm vte3 || warn "VTE paketi kurulamadı; gömülü terminal yerine sistem terminali kullanılacak."
      ;;
    zypper)
      $sudo_cmd zypper install -y python3 python3-gobject python3-gobject-Gdk gtk3
      $sudo_cmd zypper install -y libvte-2_91-0 typelib-1_0-Vte-2_91 || warn "VTE paketi kurulamadı; gömülü terminal yerine sistem terminali kullanılacak."
      ;;
    apk)
      $sudo_cmd apk add python3 py3-gobject3 gtk+3.0
      $sudo_cmd apk add vte3 || warn "VTE paketi kurulamadı; gömülü terminal yerine sistem terminali kullanılacak."
      ;;
  esac
  ok "Sistem bağımlılıkları kuruldu"
}

# -- kurulum adımları ----------------------------------------------------
install_files() {
  info "Uygulama dosyaları kopyalanıyor -> $INSTALL_DIR"
  rm -rf "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
  cp -r "$REPO_ROOT/src" "$INSTALL_DIR/"
  cp -r "$REPO_ROOT/data" "$INSTALL_DIR/"
  ok "Dosyalar kopyalandı"
}

install_launcher() {
  mkdir -p "$BIN_DIR"
  local python_bin
  python_bin="$(resolve_python_bin)"
  cat > "$LAUNCHER_PATH" <<EOF
#!/usr/bin/env bash
# $APP_DISPLAY_NAME başlatıcısı - install.sh tarafından oluşturuldu.
export PYTHONPATH="$INSTALL_DIR/src\${PYTHONPATH:+:\$PYTHONPATH}"
export SYSDEV_EXPLORER_CSS="$INSTALL_DIR/data/style.css"
exec $python_bin -m sysdev_explorer "\$@"
EOF
  chmod +x "$LAUNCHER_PATH"
  ok "Başlatıcı oluşturuldu: $LAUNCHER_PATH (yorumlayıcı: $python_bin)"
}

install_desktop_entry() {
  mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
  cp "$REPO_ROOT/data/icons/sysdev-explorer.svg" "$ICON_FILE"
  sed \
    -e "s#^Exec=.*#Exec=$LAUNCHER_PATH %U#" \
    -e "s#^Icon=.*#Icon=$APP_NAME#" \
    "$REPO_ROOT/data/sysdev-explorer.desktop" > "$DESKTOP_FILE"
  chmod +x "$DESKTOP_FILE"
  ok ".desktop girdisi oluşturuldu: $DESKTOP_FILE"

  command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
}

check_path() {
  case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
      warn "$BIN_DIR PATH içinde değil."
      warn "Terminalden '$APP_NAME' komutuyla çalıştırmak için kabuk profilinize ekleyin:"
      echo "    export PATH=\"$BIN_DIR:\$PATH\""
      ;;
  esac
}

do_install() {
  info "$APP_DISPLAY_NAME kuruluyor..."
  install_dependencies
  install_files
  install_launcher
  install_desktop_entry
  check_path
  echo
  ok "Kurulum tamamlandı!"
  echo "  Başlatmak için:      $APP_NAME"
  echo "  veya Uygulamalar menüsünden 'SysDev Explorer' araması yapın."
  echo "  Kaldırmak için:      $0 uninstall"
}

# -- kaldırma ---------------------------------------------------------------
do_uninstall() {
  info "$APP_DISPLAY_NAME kaldırılıyor..."
  if ! confirm "Devam edilsin mi?"; then
    warn "Kaldırma iptal edildi."
    exit 0
  fi

  local removed=0
  for target in "$INSTALL_DIR" "$LAUNCHER_PATH" "$DESKTOP_FILE" "$ICON_FILE"; do
    if [ -e "$target" ]; then
      rm -rf "$target"
      ok "Silindi: $target"
      removed=1
    fi
  done

  if [ "$PURGE" -eq 1 ]; then
    if [ -d "$CONFIG_DIR" ]; then
      rm -rf "$CONFIG_DIR"
      ok "Yapılandırma silindi: $CONFIG_DIR"
    fi
  elif [ -d "$CONFIG_DIR" ]; then
    warn "Yapılandırma dosyaları korundu: $CONFIG_DIR (silmek için --purge kullanın)"
  fi

  command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true

  if [ "$removed" -eq 0 ]; then
    warn "Kurulu bir $APP_DISPLAY_NAME bulunamadı."
  else
    ok "Kaldırma tamamlandı."
  fi
}

# -- durum --------------------------------------------------------------
do_status() {
  print_status_line() {
    local label="$1" path="$2"
    if [ -e "$path" ]; then
      echo "  $label: $(color '1;32' 'kurulu')  ($path)"
    else
      echo "  $label: $(color '1;33' 'yok')"
    fi
  }
  echo "$APP_DISPLAY_NAME kurulum durumu"
  print_status_line "Uygulama dosyaları" "$INSTALL_DIR"
  print_status_line "Başlatıcı         " "$LAUNCHER_PATH"
  print_status_line "Desktop girdisi   " "$DESKTOP_FILE"
  print_status_line "Simge             " "$ICON_FILE"
  print_status_line "Yapılandırma      " "$CONFIG_DIR"
}

# -- argüman ayrıştırma ----------------------------------------------------
COMMAND=""
while [ $# -gt 0 ]; do
  case "$1" in
    install|uninstall|status) COMMAND="$1" ;;
    -y|--yes) ASSUME_YES=1 ;;
    --no-deps) SKIP_DEPS=1 ;;
    --purge) PURGE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) err "Bilinmeyen seçenek: $1"; usage; exit 1 ;;
  esac
  shift
done

if [ -z "$COMMAND" ]; then
  echo "$APP_DISPLAY_NAME kurulum betiği"
  echo
  echo "  1) Kur"
  echo "  2) Kaldır"
  echo "  3) Durumu göster"
  echo "  4) Çıkış"
  echo
  read -r -p "Seçiminiz [1-4]: " choice
  case "$choice" in
    1) COMMAND=install ;;
    2) COMMAND=uninstall ;;
    3) COMMAND=status ;;
    *) exit 0 ;;
  esac
fi

case "$COMMAND" in
  install) do_install ;;
  uninstall) do_uninstall ;;
  status) do_status ;;
esac
