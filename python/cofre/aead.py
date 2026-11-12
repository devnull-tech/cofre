"""AES-256-GCM usando directamente la libcrypto (OpenSSL 3) del sistema.

Se usa ctypes en lugar del paquete python3-cryptography porque el de Sailfish
OS 5.x está enlazado con OpenSSL 3 pero compilado para 1.1 y no se puede
importar (símbolo FIPS_mode no definido). La interfaz imita a
cryptography.hazmat.primitives.ciphers.aead.AESGCM.
"""

import ctypes
import ctypes.util

_EVP_CTRL_GCM_SET_IVLEN = 0x9
_EVP_CTRL_GCM_GET_TAG = 0x10
_EVP_CTRL_GCM_SET_TAG = 0x11
TAG_LEN = 16


class InvalidTag(Exception):
    """Fallo de autenticación: datos manipulados o clave incorrecta."""


def _load():
    candidates = ["libcrypto.so.3", ctypes.util.find_library("crypto")]
    for name in candidates:
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            lib.EVP_aes_256_gcm  # comprueba que es una libcrypto válida
            return lib
        except (OSError, AttributeError):
            continue
    raise ImportError("No se encuentra libcrypto (OpenSSL 3)")


_lib = _load()

_p = ctypes.c_void_p
_int = ctypes.c_int
_pint = ctypes.POINTER(ctypes.c_int)
_buf = ctypes.c_char_p

_lib.EVP_CIPHER_CTX_new.restype = _p
_lib.EVP_CIPHER_CTX_new.argtypes = []
_lib.EVP_CIPHER_CTX_free.restype = None
_lib.EVP_CIPHER_CTX_free.argtypes = [_p]
_lib.EVP_aes_256_gcm.restype = _p
_lib.EVP_aes_256_gcm.argtypes = []
_lib.EVP_CIPHER_CTX_ctrl.restype = _int
_lib.EVP_CIPHER_CTX_ctrl.argtypes = [_p, _int, _int, _p]
for _name in ("EVP_EncryptInit_ex", "EVP_DecryptInit_ex"):
    getattr(_lib, _name).restype = _int
    getattr(_lib, _name).argtypes = [_p, _p, _p, _buf, _buf]
for _name in ("EVP_EncryptUpdate", "EVP_DecryptUpdate"):
    getattr(_lib, _name).restype = _int
    getattr(_lib, _name).argtypes = [_p, _p, _pint, _buf, _int]
for _name in ("EVP_EncryptFinal_ex", "EVP_DecryptFinal_ex"):
    getattr(_lib, _name).restype = _int
    getattr(_lib, _name).argtypes = [_p, _p, _pint]

_CIPHER = _lib.EVP_aes_256_gcm()


def _check(ok, what):
    if ok != 1:
        raise RuntimeError("OpenSSL: fallo en " + what)


class AESGCM:
    def __init__(self, key):
        if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
            raise ValueError("La clave AES-256 debe tener 32 bytes")
        self._key = bytes(key)

    def _run(self, encrypt, nonce, data, aad, tag=None):
        if len(nonce) != 12:
            raise ValueError("El nonce debe tener 12 bytes")
        init = _lib.EVP_EncryptInit_ex if encrypt else _lib.EVP_DecryptInit_ex
        update = _lib.EVP_EncryptUpdate if encrypt else _lib.EVP_DecryptUpdate
        final = _lib.EVP_EncryptFinal_ex if encrypt else _lib.EVP_DecryptFinal_ex

        ctx = _lib.EVP_CIPHER_CTX_new()
        if not ctx:
            raise MemoryError("EVP_CIPHER_CTX_new")
        try:
            outl = ctypes.c_int(0)
            _check(init(ctx, _CIPHER, None, None, None), "init")
            _check(_lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_SET_IVLEN, 12, None), "ivlen")
            _check(init(ctx, None, None, self._key, bytes(nonce)), "clave")
            if aad:
                _check(update(ctx, None, ctypes.byref(outl), bytes(aad), len(aad)), "aad")
            out = ctypes.create_string_buffer(len(data) + TAG_LEN)
            n = 0
            if data:
                _check(update(ctx, out, ctypes.byref(outl), bytes(data), len(data)), "datos")
                n = outl.value
            if not encrypt:
                tagbuf = ctypes.create_string_buffer(bytes(tag), TAG_LEN)
                _check(_lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_SET_TAG, TAG_LEN, tagbuf), "tag")
            fin = ctypes.create_string_buffer(TAG_LEN)
            if final(ctx, fin, ctypes.byref(outl)) != 1:
                if encrypt:
                    raise RuntimeError("OpenSSL: fallo en final")
                raise InvalidTag()
            result = out.raw[:n] + fin.raw[:outl.value]
            if encrypt:
                tagbuf = ctypes.create_string_buffer(TAG_LEN)
                _check(_lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_GET_TAG, TAG_LEN, tagbuf), "get tag")
                result += tagbuf.raw
            return result
        finally:
            _lib.EVP_CIPHER_CTX_free(ctx)

    def encrypt(self, nonce, data, associated_data):
        return self._run(True, nonce, data, associated_data)

    def decrypt(self, nonce, data, associated_data):
        if len(data) < TAG_LEN:
            raise InvalidTag()
        return self._run(False, nonce, data[:-TAG_LEN], associated_data, data[-TAG_LEN:])
