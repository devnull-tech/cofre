"""Información de imágenes sin dependencias: miniatura EXIF y orientación.

Las fotos de cámara (JPEG) llevan al principio un bloque EXIF con una
miniatura de unos 10 KB y la orientación con la que se hizo la foto. Leer solo
el principio del fichero permite mostrar miniaturas sin descifrar la foto entera.
"""

import struct

HEAD_SIZE = 256 * 1024          # el bloque EXIF cabe siempre aquí (máx. 64 KB)
SMALL_IMAGE = 3 * 1024 * 1024   # sin miniatura EXIF, se muestra entera si es pequeña

ORIENTATION_ANGLE = {1: 0, 2: 0, 3: 180, 4: 180, 5: 90, 6: 90, 7: 270, 8: 270}


def exif_info(data):
    """Devuelve ((inicio, longitud) de la miniatura dentro de data, o None,
    orientación EXIF 1..8)."""
    if data[:2] != b"\xff\xd8":
        return None, 1
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker in (0xD9, 0xDA):  # fin de imagen / comienzo de los datos
            break
        if 0xD0 <= marker <= 0xD7 or marker in (0x01, 0xFF):
            i += 2 if marker != 0xFF else 1
            continue
        seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\0\0":
            parsed = _parse_tiff(data, i + 10, min(len(data), i + 2 + seglen))
            if parsed is not None:
                return parsed
        i += 2 + seglen
    return None, 1


def _parse_tiff(data, base, end):
    tiff = data[base:end]
    if len(tiff) < 8:
        return None
    bo = {b"II": "<", b"MM": ">"}.get(tiff[:2])
    if bo is None or struct.unpack(bo + "H", tiff[2:4])[0] != 42:
        return None
    entries, next_ifd = _read_ifd(tiff, struct.unpack(bo + "I", tiff[4:8])[0], bo)
    if entries is None:
        return None
    orientation = entries.get(0x0112, 1)
    if orientation not in ORIENTATION_ANGLE:
        orientation = 1
    thumb = None
    if next_ifd:
        ifd1, _ = _read_ifd(tiff, next_ifd, bo)
        if ifd1 and 0x0201 in ifd1 and 0x0202 in ifd1:
            off, length = ifd1[0x0201], ifd1[0x0202]
            if length > 0 and off + length <= len(tiff) and tiff[off:off + 2] == b"\xff\xd8":
                thumb = (base + off, length)
    return thumb, orientation


def _read_ifd(tiff, off, bo):
    if off <= 0 or off + 2 > len(tiff):
        return None, 0
    n = struct.unpack(bo + "H", tiff[off:off + 2])[0]
    end = off + 2 + n * 12
    if end + 4 > len(tiff):
        return None, 0
    entries = {}
    for k in range(n):
        e = off + 2 + k * 12
        tag, typ, count = struct.unpack(bo + "HHI", tiff[e:e + 8])
        if count != 1:
            continue
        if typ == 3:    # SHORT
            entries[tag] = struct.unpack(bo + "H", tiff[e + 8:e + 10])[0]
        elif typ == 4:  # LONG
            entries[tag] = struct.unpack(bo + "I", tiff[e + 8:e + 12])[0]
    return entries, struct.unpack(bo + "I", tiff[end:end + 4])[0]


def analyze(head, size):
    """Decide cómo mostrar la miniatura de una imagen a partir de su principio.
    Devuelve (modo, orientación): modo "exif", "full" o "" (usar icono)."""
    thumb, orientation = exif_info(head)
    if thumb is not None:
        return "exif", orientation
    return ("full" if size <= SMALL_IMAGE else ""), orientation
