"""Vídeo y audio: copia descifrada temporal en memoria RAM.

El reproductor de Qt solo abre ficheros o URLs, así que el vídeo se descifra a
un fichero en un tmpfs. Dentro del sandbox de Sailjail, XDG_RUNTIME_DIR es un
tmpfs privado de la app: otras apps no lo ven y nunca se escribe en el
almacenamiento. Si la carpeta no es un tmpfs, se niega a descifrar.

Solo existe una copia a la vez. El descifrado ocurre en un hilo aparte y se
cancela en cuanto se pide otro fichero o se cierra (p. ej. al pasar de largo un
vídeo en la galería). La copia se borra al cerrar el visor, al bloquear el cofre
y al arrancar la app.
"""

import os
import secrets
import threading

from .vault import VaultError

_RAM_FS = {"tmpfs", "ramfs"}
_MARGIN = 32 * 1024 * 1024  # memoria que se deja libre en el tmpfs


class _Cancelled(Exception):
    pass


def filesystem_type(path):
    """Tipo de sistema de ficheros del punto de montaje que contiene path."""
    path = os.path.realpath(path)
    best, fstype = "", None
    with open("/proc/self/mounts") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 3:
                continue
            mnt = parts[1].replace("\\040", " ")
            if (path == mnt or path.startswith(mnt.rstrip("/") + "/")) and len(mnt) >= len(best):
                best, fstype = mnt, parts[2]
    return fstype


def _remove(path):
    if path:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


class MediaCache:
    def __init__(self, vault, directory, require_ram=True):
        self.vault = vault
        self.directory = directory
        self.require_ram = require_ram
        self._lock = threading.Lock()
        self._gen = 0             # cambia con cada petición: invalida las anteriores
        self.current = None       # ruta de la copia lista
        self.current_fid = None
        self.pending_fid = None   # fichero que se está descifrando

    def _prepare_dir(self):
        os.makedirs(self.directory, mode=0o700, exist_ok=True)
        os.chmod(self.directory, 0o700)
        if self.require_ram and filesystem_type(self.directory) not in _RAM_FS:
            raise VaultError("no_secure_memory")

    def open_async(self, fid, on_ready, on_error):
        """Empieza a descifrar fid. Llama a on_ready(fid, ruta) o a
        on_error(fid, excepción) desde otro hilo, salvo que se cancele antes."""
        with self._lock:
            self._gen += 1
            gen = self._gen
            old, self.current, self.current_fid = self.current, None, None
            self.pending_fid = fid
        _remove(old)
        threading.Thread(target=self._worker, args=(fid, gen, on_ready, on_error),
                         name="cofre-media", daemon=True).start()

    def _check(self, gen):
        if self._gen != gen:
            raise _Cancelled()

    def _worker(self, fid, gen, on_ready, on_error):
        path = None
        try:
            entry = self.vault.entry(fid)
            self._prepare_dir()
            try:
                st = os.statvfs(self.directory)
                free = st.f_bavail * st.f_frsize
            except OSError:
                # No disponible en algunos entornos (p. ej. el de compilación del SDK).
                # Si la memoria se llena, la escritura falla y la copia se borra.
                free = None
            if free is not None and entry["size"] + _MARGIN > free:
                raise VaultError("too_big", mb=entry["size"] // 1048576)
            ext = os.path.splitext(entry["name"])[1].lower()
            if not ext.isascii() or len(ext) > 8:
                ext = ""
            path = os.path.join(self.directory, secrets.token_hex(16) + ext)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out, self.vault.open_reader(fid) as reader:
                for piece in reader.iter_range(0, reader.size):
                    self._check(gen)
                    out.write(piece)
            with self._lock:
                self._check(gen)
                self.current, self.current_fid, self.pending_fid = path, fid, None
            on_ready(fid, path)
        except _Cancelled:
            _remove(path)
        except Exception as e:
            _remove(path)
            with self._lock:
                stale = self._gen != gen
                if not stale:
                    self.pending_fid = None
            if not stale:
                on_error(fid, e)

    def close(self, fid=None):
        """Cancela el descifrado y borra la copia. Con fid, solo si se refiere a
        ese fichero (para no borrar la del visor que se acaba de abrir)."""
        with self._lock:
            if fid is not None and fid not in (self.current_fid, self.pending_fid):
                return
            self._gen += 1
            old, self.current, self.current_fid, self.pending_fid = self.current, None, None, None
        _remove(old)

    def clear(self):
        """Borra cualquier resto (p. ej. si la app se cerró de golpe)."""
        self.close()
        if os.path.isdir(self.directory):
            for name in os.listdir(self.directory):
                _remove(os.path.join(self.directory, name))
