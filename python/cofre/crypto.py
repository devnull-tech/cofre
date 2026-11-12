"""Primitivas criptográficas de Cofre.

Diseño:
- La contraseña maestra se pasa por scrypt para obtener una clave (KEK).
- La KEK envuelve (AES-256-GCM) una clave maestra aleatoria de 32 bytes.
  Cambiar la contraseña solo re-envuelve la clave maestra; los ficheros no
  se vuelven a cifrar.
- Cada fichero usa su propia clave: HMAC-SHA256(maestra, "cofre-file-v1" || sal),
  con una sal aleatoria de 16 bytes guardada en la cabecera.
- El contenido se cifra en bloques de 256 KiB con AES-256-GCM. El nonce de cada
  bloque es (número de bloque, indicador de último bloque), de modo que no se
  pueden reordenar, duplicar ni truncar bloques sin que falle la autenticación.
  Los bloques permiten descifrar trozos sueltos (avance rápido en vídeos).
"""

import hashlib
import hmac
import os
import struct

from .aead import AESGCM, InvalidTag

KEY_LEN = 32
NONCE_LEN = 12
TAG_LEN = 16
CHUNK_SIZE = 256 * 1024

MAGIC = b"COF1"
FORMAT_VERSION = 1
_HEADER = struct.Struct(">4sBI16s")  # magic, versión, tamaño de bloque, sal
HEADER_LEN = _HEADER.size

_MIN_CHUNK = 1024
_MAX_CHUNK = 16 * 1024 * 1024


class CryptoError(Exception):
    """Datos corruptos, manipulados o clave incorrecta."""


def derive_kek(password, salt, n, r, p):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                          maxmem=256 * 1024 * 1024, dklen=KEY_LEN)


def seal(key, data, aad):
    nonce = os.urandom(NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def unseal(key, blob, aad):
    if len(blob) < NONCE_LEN + TAG_LEN:
        raise CryptoError("datos truncados")
    try:
        return AESGCM(key).decrypt(blob[:NONCE_LEN], blob[NONCE_LEN:], aad)
    except InvalidTag:
        raise CryptoError("autenticación fallida") from None


def _file_key(master, salt):
    return hmac.new(master, b"cofre-file-v1" + salt, hashlib.sha256).digest()


def _chunk_nonce(index, last):
    return struct.pack(">QB3x", index, 1 if last else 0)


def _read_full(src, n):
    parts = []
    remaining = n
    while remaining > 0:
        data = src.read(remaining)
        if not data:
            break
        parts.append(data)
        remaining -= len(data)
    return b"".join(parts)


def encrypt_stream(master, file_id, src, dst, progress=None):
    """Cifra src (fichero binario) en dst. Devuelve el tamaño en claro."""
    salt = os.urandom(16)
    header = _HEADER.pack(MAGIC, FORMAT_VERSION, CHUNK_SIZE, salt)
    aad = header + file_id.encode("ascii")
    aes = AESGCM(_file_key(master, salt))
    dst.write(header)

    index = 0
    done = 0
    cur = _read_full(src, CHUNK_SIZE)
    while True:
        nxt = _read_full(src, CHUNK_SIZE) if len(cur) == CHUNK_SIZE else b""
        last = not nxt
        dst.write(aes.encrypt(_chunk_nonce(index, last), cur, aad))
        done += len(cur)
        index += 1
        if progress is not None:
            progress(done)
        if last:
            return done
        cur = nxt


class BlobReader:
    """Acceso aleatorio de solo lectura a un fichero cifrado."""

    def __init__(self, master, file_id, path):
        self._f = open(path, "rb")
        try:
            header = self._f.read(HEADER_LEN)
            if len(header) != HEADER_LEN:
                raise CryptoError("cabecera truncada")
            magic, version, chunk, salt = _HEADER.unpack(header)
            if magic != MAGIC or version != FORMAT_VERSION:
                raise CryptoError("formato desconocido")
            if not _MIN_CHUNK <= chunk <= _MAX_CHUNK:
                raise CryptoError("tamaño de bloque inválido")
            self.chunk_size = chunk
            self._stride = chunk + TAG_LEN
            self._aad = header + file_id.encode("ascii")
            self._aes = AESGCM(_file_key(master, salt))

            data_len = os.fstat(self._f.fileno()).st_size - HEADER_LEN
            if data_len < TAG_LEN:
                raise CryptoError("fichero truncado")
            self.chunks = -(-data_len // self._stride)
            self._last_len = data_len - (self.chunks - 1) * self._stride
            if self._last_len < TAG_LEN:
                raise CryptoError("fichero truncado")
            self.size = data_len - self.chunks * TAG_LEN
        except Exception:
            self._f.close()
            raise

    def read_chunk(self, index):
        last = index == self.chunks - 1
        self._f.seek(HEADER_LEN + index * self._stride)
        ct = self._f.read(self._last_len if last else self._stride)
        try:
            return self._aes.decrypt(_chunk_nonce(index, last), ct, self._aad)
        except InvalidTag:
            raise CryptoError("bloque %d corrupto o manipulado" % index) from None

    def iter_range(self, start, end):
        """Genera el texto en claro del rango [start, end)."""
        end = min(end, self.size)
        index = start // self.chunk_size
        while start < end:
            data = self.read_chunk(index)
            offset = start - index * self.chunk_size
            piece = data[offset:offset + (end - start)]
            if not piece:
                break
            yield piece
            start += len(piece)
            index += 1

    def read(self, limit=None):
        end = self.size if limit is None else min(limit, self.size)
        return b"".join(self.iter_range(0, end))

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
