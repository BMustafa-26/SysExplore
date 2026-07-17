# SysDev Explorer

Ekteki tasarıma dayanan, Linux üzerinde **native** çalışan bir GTK3 (Python /
PyGObject) dosya yöneticisi: konum/disk/kısayol kenar çubuğu, sekmeli
gezinme, breadcrumb, ızgara/liste görünümü, Genel/İzinler/Paylaşım sekmeli
özellik paneli, Git durumu paneli, dosya önizlemesi, gömülü terminal (VTE),
hızlı işlemler ve son kullanılanlar paneli içerir.

Ayrıca: arka planda (UI'yi dondurmadan) kopyala/taşı/sil işlemleri —
ilerleme çubuğu, iptal ve çakışma çözümü (atla/değiştir/yeniden adlandır)
ile; **Geri Al / Yinele** (Ctrl+Z / Ctrl+Shift+Z); gerçek **Çöp Kutusu**
gezinme, geri yükleme ve kalıcı silme (GVFS gerektirmez); gizli dosya
göster/gizle (Ctrl+H); adres çubuğuna yazarak gitme (Ctrl+L); çoklu seçimde
toplam boyut/sayı özeti; arşiv **sıkıştır/çıkart** (zip/tar, zip-slip
korumalı); çalıştırılabilir dosyalarda çalıştır/düzenle onayı; ızgara
görünümünde gerçek resim küçük resimleri; USB gibi çıkarılabilir diskler
için bağla/çıkar; `smb://`, `sftp://`, `ftp://` ağ konumlarına bağlanma;
ve Tercihler / Hakkında penceresi.

## Kurulum

```bash
./install.sh install
```

veya argümansız çalıştırıp interaktif menüden "Kur" seçeneğini seçin:

```bash
./install.sh
```

Betik:
- Eksik sistem bağımlılıklarını (GTK3 + PyGObject, isteğe bağlı VTE terminal
  kütüphanesi) `apt`/`dnf`/`pacman`/`zypper`/`apk` ile tespit edip kurar,
- Uygulamayı `~/.local/share/sysdev-explorer` altına kopyalar (kullanıcı
  bazlı, sudo gerektirmez),
- `~/.local/bin/sysdev-explorer` başlatıcısını oluşturur,
- Uygulamalar menüsünde görünmesi için `.desktop` girdisi ve simge kurar.

Kurulumdan sonra `sysdev-explorer` komutuyla veya uygulama menüsünden
başlatabilirsiniz.

### Seçenekler

| Seçenek | Açıklama |
| --- | --- |
| `-y`, `--yes` | Tüm sorulara otomatik "evet" |
| `--no-deps` | Sistem paketi kurulumunu atla |
| `--purge` | (uninstall ile) `~/.config/sysdev-explorer` yapılandırmasını da sil |

## Kaldırma

```bash
./install.sh uninstall
```

Kurulum dizinini, başlatıcıyı, `.desktop` girdisini ve simgeyi kaldırır.
Yapılandırma (kısayollar vb.) varsayılan olarak korunur; tamamen silmek için
`--purge` kullanın.

## Durum

```bash
./install.sh status
```

## Geliştirme (kurulum yapmadan çalıştırma)

```bash
./bin/sysdev-explorer
```

Bağımlılıklar: `python3`, `python3-gi`, GTK3 typelib'i (`gir1.2-gtk-3.0`) ve
isteğe bağlı gömülü terminal için `gir1.2-vte-2.91`. VTE kurulu değilse
uygulama otomatik olarak sistem terminalini açan bir düğmeye geçer.

## Klasör yapısı

```
install.sh              kurulum / kaldırma betiği
bin/sysdev-explorer      depo içinden çalıştırma betiği (dev)
data/                    CSS tema, .desktop şablonu, simge
src/sysdev_explorer/     uygulama kaynak kodu
```
