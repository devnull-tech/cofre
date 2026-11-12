Name:       harbour-cofre
Summary:    Encrypted vault for your files
Version:    0.1.0
Release:    1
License:    GPLv3+
BuildArch:  noarch
URL:        https://github.com/devnull-tech/cofre
Source0:    %{name}-%{version}.tar.bz2

# Harbour solo admite como requisito explícito un conjunto reducido de paquetes.
# El resto de lo que usa Cofre viene de serie en Sailfish OS y no se declara:
#   python3-base, openssl-libs (libcrypto 3, vía ctypes),
#   qt5-qtmultimedia-plugin-mediaservice-gstmediaplayer, gstreamer1.0-plugins-good
#   (reproducción de vídeo y audio) y sailfish-components-pickers-qt5 (selectores).
Requires:   sailfishsilica-qt5 >= 0.10.9
Requires:   libsailfishapp-launcher
Requires:   pyotherside-qml-plugin-python3-qt5
Requires:   qt5-qtdeclarative-import-multimedia

# Para ejecutar las pruebas en %%check con las versiones del teléfono
# y generar las traducciones.
BuildRequires: python3-base
BuildRequires: openssl-libs >= 3.0
BuildRequires: qt5-qttools-linguist

%description
Cofre keeps your photos, videos, documents and any other files encrypted
with AES-256-GCM under a master password. You can browse folders and view
photos, videos, audio and text without the decrypted content ever being
written to storage.

%prep
%setup -q -n %{name}-%{version}

%build
# Traducciones de la interfaz (el inglés es el idioma base, en el código)
for ts in translations/*.ts; do
    lrelease -silent "$ts" -qm "${ts%.ts}.qm"
done

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}%{_datadir}/%{name}
cp -r qml python %{buildroot}%{_datadir}/%{name}/
find %{buildroot}%{_datadir}/%{name} -name __pycache__ -prune -exec rm -rf {} +
install -m 644 LICENSE %{buildroot}%{_datadir}/%{name}/LICENSE
install -D -m 644 %{name}.desktop %{buildroot}%{_datadir}/applications/%{name}.desktop
mkdir -p %{buildroot}%{_datadir}/%{name}/translations
install -m 644 translations/*.qm %{buildroot}%{_datadir}/%{name}/translations/
for size in 86 108 128 172; do
    install -D -m 644 icons/${size}x${size}/%{name}.png \
        %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/%{name}.png
done

%check
python3 -m unittest discover -s tests

%files
%defattr(-,root,root,-)
%{_datadir}/%{name}
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/*/apps/%{name}.png

%changelog
* Wed Nov 11 2026 Leandro Puentes <lpuentesrivas@gmail.com> - 0.1.0-1
- First release.
- Encrypted vault with master password (scrypt + AES-256-GCM).
- Folders, folder import with subfolders, multiple selection.
- Gallery for photos and videos, text and audio viewers.
- English and Spanish translations.
