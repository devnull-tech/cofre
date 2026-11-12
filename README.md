# Cofre

Encrypted vault for your files on Sailfish OS. · *Almacén cifrado de ficheros para Sailfish OS.*

<p>
<img src="publicacion/harbour/screenshot-1-folder-with-thumbnails.png" width="220">
<img src="publicacion/harbour/screenshot-2-gallery.png" width="220">
<img src="publicacion/harbour/screenshot-3-multiple-selection.png" width="220">

</p>

## English

Cofre keeps your photos, videos, documents and any other files encrypted under a master password.

- **Encryption:** AES-256-GCM in 256 KiB authenticated chunks, using a per-file key derived from a random master key. The master key is wrapped with a key derived from your password with scrypt. File names and folders are stored in an encrypted index.
- **No plaintext on storage:** photos are decrypted in memory (PyOtherSide image provider). Videos and audio are decrypted to a private in-memory (tmpfs) copy inside the app sandbox, which is deleted when the viewer closes, when the vault locks and when the app starts.
- **Features:** folders, importing whole folders, optionally deleting originals, multiple selection, a gallery for photos and videos, viewers for text and audio, export, and auto-lock.
- **Languages:** English and Spanish.

If you forget your password, your files cannot be recovered.

### Building

You need the [Sailfish SDK](https://docs.sailfishos.org/Tools/Sailfish_SDK/).

```
sfdk config target=SailfishOS-5.1.0.11-aarch64
sfdk build          # also runs the test suite
sfdk check RPMS/harbour-cofre-*.noarch.rpm
```

The core can be tested on any Linux with Python 3 and OpenSSL 3: `python3 -m unittest discover -s tests`.

### Project layout

- `python/cofre/`: vault, encryption (OpenSSL through ctypes), image info, temporary media copies
- `python/cofre_bridge.py`: functions called from QML through PyOtherSide
- `qml/`: user interface (Sailfish Silica)
- `translations/`: translations (`tools/translate_es.py` fills in the Spanish one)
- `tests/`: automated tests

## Español

Cofre guarda tus fotos, vídeos, documentos y cualquier otro fichero cifrados con una contraseña maestra. Todo el contenido, incluidos los nombres de los ficheros y las carpetas, se cifra con AES-256-GCM. Lo descifrado nunca se escribe en el almacenamiento: las fotos se descifran en memoria, y los vídeos se reproducen desde una copia privada en RAM que se borra al cerrarlos.

Si olvidas la contraseña, no hay forma de recuperar los ficheros.

## License

GPLv3 or later. See [LICENSE](LICENSE).

© 2026 Leandro Puentes · Sactu
