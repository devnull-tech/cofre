"""Gestión del cofre: contraseña maestra, índice cifrado y ficheros."""

import base64
import json
import mimetypes
import os
import threading
import time
import uuid

from . import crypto, imageinfo

MIN_PASSWORD = 8
KDF_DEFAULT = {"name": "scrypt", "n": 2 ** 15, "r": 8, "p": 1}

_AAD_MASTER = b"cofre-master-v1"
_AAD_INDEX = b"cofre-index-v1"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
VIDEO_EXT = {".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".3gp", ".ogv"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wav"}
TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".log", ".ini",
            ".conf", ".cfg", ".yaml", ".yml", ".toml", ".py", ".sh", ".html",
            ".htm", ".js", ".css", ".c", ".h", ".cpp", ".qml", ".srt", ".vcf",
            ".ics", ".tex", ".rst"}


class VaultError(Exception):
    """Error para el usuario. La interfaz traduce el código (ver errorText en
    harbour-cofre.qml); el texto en inglés es solo para los registros."""

    def __init__(self, code, **params):
        self.code = code
        self.params = params
        detail = ", ".join("%s=%s" % kv for kv in sorted(params.items()))
        super().__init__(code + (" (%s)" % detail if detail else ""))


class WrongPassword(VaultError):
    def __init__(self):
        super().__init__("wrong_password")


def classify(name):
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in TEXT_EXT:
        return "text"
    mime = mimetypes.guess_type(name)[0] or ""
    if mime.startswith("text/"):
        return "text"
    return "other"


def text(value):
    """Texto Unicode limpio a partir de bytes o de un str con escapes.

    En el sandbox de Sailfish no hay locale UTF-8, así que Python decodifica los
    nombres de fichero como ASCII con 'surrogateescape' ("Montaña" llega como
    'Monta\\udcc3\\udcb1a'). Esos caracteres no se pueden guardar en JSON ni
    pasar a QML (PyOtherSide se cae), así que se recuperan aquí como UTF-8.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def fspath(value):
    """Ruta del sistema de ficheros como bytes UTF-8, independiente del locale."""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8", "surrogateescape")


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _unb64(text):
    return base64.b64decode(text.encode("ascii"))


def _atomic_write(path, data):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _check_password(password):
    if len(password) < MIN_PASSWORD:
        raise VaultError("password_too_short", min=MIN_PASSWORD)


class Vault:
    def __init__(self, root):
        self.root = root
        self.blob_dir = os.path.join(root, "blobs")
        self.meta_path = os.path.join(root, "vault.json")
        self.index_path = os.path.join(root, "index.bin")
        self._lock = threading.RLock()
        self._key = None
        self._index = None
        self._saved = None

    # --- estado -------------------------------------------------------------

    def exists(self):
        return os.path.exists(self.meta_path)

    @property
    def unlocked(self):
        return self._key is not None

    def _require_unlocked(self):
        if self._key is None:
            raise VaultError("locked")

    # --- contraseña ---------------------------------------------------------

    @staticmethod
    def _wrap_master(master, password):
        salt = os.urandom(16)
        kdf = dict(KDF_DEFAULT, salt=_b64(salt))
        kek = crypto.derive_kek(password, salt, kdf["n"], kdf["r"], kdf["p"])
        return {"format": "cofre", "version": 1, "kdf": kdf,
                "master": _b64(crypto.seal(kek, master, _AAD_MASTER))}

    def _unwrap_master(self, password):
        with open(self.meta_path, "rb") as f:
            meta = json.loads(f.read().decode("utf-8"))
        kdf = meta["kdf"]
        if kdf.get("name") != "scrypt" or not 2 ** 10 <= kdf["n"] <= 2 ** 22:
            raise VaultError("bad_vault_params")
        kek = crypto.derive_kek(password, _unb64(kdf["salt"]), kdf["n"], kdf["r"], kdf["p"])
        try:
            return crypto.unseal(kek, _unb64(meta["master"]), _AAD_MASTER)
        except crypto.CryptoError:
            raise WrongPassword() from None

    def create(self, password):
        with self._lock:
            if self.exists():
                raise VaultError("already_exists")
            _check_password(password)
            os.makedirs(self.blob_dir, mode=0o700, exist_ok=True)
            master = os.urandom(crypto.KEY_LEN)
            meta = self._wrap_master(master, password)
            self._key = master
            self._index = {"version": 2, "files": {}, "folders": {}}
            self._save_index()
            _atomic_write(self.meta_path, json.dumps(meta).encode("utf-8"))

    def unlock(self, password):
        master = self._unwrap_master(password)
        with open(self.index_path, "rb") as f:
            blob = f.read()
        try:
            index = json.loads(crypto.unseal(master, blob, _AAD_INDEX).decode("utf-8"))
        except crypto.CryptoError:
            raise VaultError("index_damaged") from None
        with self._lock:
            os.makedirs(self.blob_dir, mode=0o700, exist_ok=True)
            self._key = master
            self._index = self._upgrade(index)
            self._saved = json.dumps(self._index, ensure_ascii=False).encode("utf-8")

    def lock(self):
        with self._lock:
            self._key = None
            self._index = None
            self._saved = None

    def change_password(self, old, new):
        _check_password(new)
        master = self._unwrap_master(old)
        meta = self._wrap_master(master, new)
        with self._lock:
            _atomic_write(self.meta_path, json.dumps(meta).encode("utf-8"))

    # --- índice -------------------------------------------------------------

    @staticmethod
    def _upgrade(index):
        """Completa índices de versiones anteriores (v1 no tenía carpetas)."""
        index.setdefault("folders", {})
        for e in index["files"].values():
            e.setdefault("folder", "")
        index["version"] = 2
        return index

    def _save_index(self):
        """Guarda el índice. Si algo falla, el índice en memoria vuelve al último
        estado guardado para que nunca quede a medias."""
        try:
            data = json.dumps(self._index, ensure_ascii=False).encode("utf-8")
            _atomic_write(self.index_path, crypto.seal(self._key, data, _AAD_INDEX))
        except Exception as e:
            if self._saved is not None:
                self._index = json.loads(self._saved.decode("utf-8"))
            raise VaultError("index_save_failed", detail=text(str(e))) from e
        self._saved = data

    def _blob_path(self, fid):
        if len(fid) != 32 or any(c not in "0123456789abcdef" for c in fid):
            raise VaultError("invalid_id")
        return os.path.join(self.blob_dir, fid + ".cof")

    def list(self, folder=None):
        """Ficheros de una carpeta ("" = raíz), o de todo el cofre si folder es None."""
        with self._lock:
            self._require_unlocked()
            if folder:
                self._folder(folder)
            files = [dict(e, id=fid) for fid, e in self._index["files"].items()
                     if folder is None or e["folder"] == (folder or "")]
        missing = [e for e in files if e["kind"] == "image" and "thumb" not in e]
        if missing:
            self._fill_image_info(missing)
        files.sort(key=lambda e: e["added"], reverse=True)
        return files

    def _fill_image_info(self, entries):
        """Calcula miniatura y orientación de imágenes importadas antes de que
        existiera esta información (o renombradas a una extensión de imagen)."""
        for e in entries:
            try:
                head = self.read_bytes(e["id"], imageinfo.HEAD_SIZE)
                e["thumb"], e["orientation"] = imageinfo.analyze(head, e["size"])
            except Exception:
                e["thumb"], e["orientation"] = "", 1
        with self._lock:
            for e in entries:
                stored = self._index["files"].get(e["id"])
                if stored is not None:
                    stored["thumb"], stored["orientation"] = e["thumb"], e["orientation"]
            self._save_index()

    def thumbnail(self, fid):
        """Bytes JPEG/PNG para la miniatura de una imagen, o None."""
        e = self.entry(fid)
        if e.get("thumb") == "full":
            return self.read_bytes(fid)
        head = self.read_bytes(fid, imageinfo.HEAD_SIZE)
        thumb, _ = imageinfo.exif_info(head)
        if thumb is None:
            return None
        start, length = thumb
        return head[start:start + length]

    # --- carpetas -----------------------------------------------------------

    def _folder(self, folder_id):
        f = self._index["folders"].get(folder_id)
        if f is None:
            raise VaultError("folder_not_found")
        return f

    def _check_parent(self, parent):
        if parent:
            self._folder(parent)
        return parent or ""

    def _unique_folder_name(self, name, parent, exclude=None):
        taken = {f["name"].casefold() for i, f in self._index["folders"].items()
                 if f["parent"] == parent and i != exclude}
        candidate, n = name, 2
        while candidate.casefold() in taken:
            candidate = "%s (%d)" % (name, n)
            n += 1
        return candidate

    @staticmethod
    def _clean_name(name):
        name = text(name).strip().replace("/", "-")
        if not name or name in (".", ".."):
            raise VaultError("invalid_name")
        return name

    def folders(self, parent=""):
        """Subcarpetas directas de parent, con su número de elementos."""
        with self._lock:
            self._require_unlocked()
            parent = self._check_parent(parent)
            counts = {}
            for e in self._index["files"].values():
                counts[e["folder"]] = counts.get(e["folder"], 0) + 1
            for f in self._index["folders"].values():
                counts[f["parent"]] = counts.get(f["parent"], 0) + 1
            result = [dict(f, id=i, count=counts.get(i, 0))
                      for i, f in self._index["folders"].items() if f["parent"] == parent]
        result.sort(key=lambda f: f["name"].casefold())
        return result

    def folder_path(self, folder_id):
        """Ruta desde la raíz: [{"id", "name"}, ...]."""
        with self._lock:
            self._require_unlocked()
            path = []
            while folder_id:
                f = self._folder(folder_id)
                path.insert(0, {"id": folder_id, "name": f["name"]})
                folder_id = f["parent"]
            return path

    def folder_tree(self, exclude=None):
        """Todas las carpetas en orden de árbol, con su profundidad.
        Omite las carpetas de exclude (un id o una lista) y sus descendientes:
        son destinos no válidos al moverlas."""
        if isinstance(exclude, str):
            exclude = [exclude]
        exclude = set(exclude or [])
        with self._lock:
            self._require_unlocked()
            children = {}
            for i, f in self._index["folders"].items():
                children.setdefault(f["parent"], []).append(i)
            out = []

            def walk(parent, depth):
                for i in sorted(children.get(parent, []),
                                key=lambda i: self._index["folders"][i]["name"].casefold()):
                    if i in exclude:
                        continue
                    out.append({"id": i, "name": self._index["folders"][i]["name"], "depth": depth})
                    walk(i, depth + 1)

            walk("", 0)
            return out

    def create_folder(self, name, parent=""):
        name = self._clean_name(name)
        with self._lock:
            self._require_unlocked()
            parent = self._check_parent(parent)
            folder_id = uuid.uuid4().hex
            self._index["folders"][folder_id] = {
                "name": self._unique_folder_name(name, parent),
                "parent": parent, "created": time.time()}
            self._save_index()
            return folder_id

    def rename_folder(self, folder_id, name):
        name = self._clean_name(name)
        with self._lock:
            self._require_unlocked()
            f = self._folder(folder_id)
            f["name"] = self._unique_folder_name(name, f["parent"], exclude=folder_id)
            self._save_index()

    def move_folder(self, folder_id, parent):
        with self._lock:
            self._require_unlocked()
            f = self._folder(folder_id)
            parent = self._check_parent(parent)
            p = parent
            while p:
                if p == folder_id:
                    raise VaultError("move_into_itself")
                p = self._index["folders"][p]["parent"]
            f["parent"] = parent
            f["name"] = self._unique_folder_name(f["name"], parent, exclude=folder_id)
            self._save_index()

    def delete_folder(self, folder_id):
        """Borra la carpeta con todo su contenido. Devuelve cuántos ficheros se borraron."""
        with self._lock:
            self._require_unlocked()
            self._folder(folder_id)
            doomed = {folder_id}
            changed = True
            while changed:
                changed = False
                for i, f in self._index["folders"].items():
                    if f["parent"] in doomed and i not in doomed:
                        doomed.add(i)
                        changed = True
            files = [fid for fid, e in self._index["files"].items() if e["folder"] in doomed]
            for fid in files:
                del self._index["files"][fid]
            for i in doomed:
                del self._index["folders"][i]
            self._save_index()
        for fid in files:
            try:
                os.remove(self._blob_path(fid))
            except FileNotFoundError:
                pass
        return len(files)

    def move_file(self, fid, folder):
        with self._lock:
            self.entry(fid)
            self._index["files"][fid]["folder"] = self._check_parent(folder)
            self._save_index()

    def entry(self, fid):
        with self._lock:
            self._require_unlocked()
            e = self._index["files"].get(fid)
            if e is None:
                raise VaultError("file_not_found")
            return dict(e, id=fid)

    # --- operaciones con ficheros --------------------------------------------

    def import_file(self, path, progress=None, folder=""):
        with self._lock:
            self._require_unlocked()
            folder = self._check_parent(folder)
            key = self._key
        path = fspath(path)
        name = text(os.path.basename(path))
        fid = uuid.uuid4().hex
        blob = self._blob_path(fid)
        tmp = blob + ".part"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as dst, open(path, "rb") as src:
                size = crypto.encrypt_stream(key, fid, src, dst, progress)
                dst.flush()
                os.fsync(dst.fileno())
            os.replace(tmp, blob)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        entry = {"name": name, "size": size, "kind": classify(name),
                 "mime": mimetypes.guess_type(name)[0] or "application/octet-stream",
                 "added": time.time(), "folder": folder}
        if entry["kind"] == "image":
            try:
                with open(path, "rb") as src:
                    entry["thumb"], entry["orientation"] = imageinfo.analyze(
                        src.read(imageinfo.HEAD_SIZE), size)
            except OSError:
                pass
        with self._lock:
            if self._key is not key:
                os.remove(blob)
                raise VaultError("locked_during_import")
            self._index["files"][fid] = entry
            self._save_index()
        return dict(entry, id=fid)

    def open_reader(self, fid):
        with self._lock:
            self.entry(fid)
            return crypto.BlobReader(self._key, fid, self._blob_path(fid))

    def read_bytes(self, fid, limit=None):
        with self.open_reader(fid) as reader:
            return reader.read(limit)

    def export(self, fid, dest_dir):
        """Descifra el fichero en dest_dir. Devuelve la ruta creada (como texto)."""
        name = self.entry(fid)["name"]
        dest_dir = fspath(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)
        base, ext = os.path.splitext(name)
        dest = os.path.join(dest_dir, name.encode("utf-8"))
        n = 1
        while os.path.exists(dest):
            dest = os.path.join(dest_dir, ("%s (%d)%s" % (base, n, ext)).encode("utf-8"))
            n += 1
        tmp = dest + b".part"
        try:
            with self.open_reader(fid) as reader, open(tmp, "wb") as out:
                for piece in reader.iter_range(0, reader.size):
                    out.write(piece)
            os.replace(tmp, dest)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        return text(dest)

    def export_folder(self, folder_id, dest_dir):
        """Descifra una carpeta del cofre, con sus subcarpetas, dentro de dest_dir.
        Devuelve (ruta creada como texto, número de ficheros exportados)."""
        name = self._folder_info(folder_id)["name"]
        dest_dir = fspath(dest_dir)
        target = os.path.join(dest_dir, name.encode("utf-8"))
        n = 1
        while os.path.exists(target):
            target = os.path.join(dest_dir, ("%s (%d)" % (name, n)).encode("utf-8"))
            n += 1
        count = self._export_tree(folder_id, target)
        return text(target), count

    def _export_tree(self, folder_id, target):
        os.makedirs(target, exist_ok=True)
        count = 0
        for e in self.list(folder_id):
            self.export(e["id"], target)
            count += 1
        for f in self.folders(folder_id):
            count += self._export_tree(f["id"], os.path.join(target, f["name"].encode("utf-8")))
        return count

    def _folder_info(self, folder_id):
        with self._lock:
            self._require_unlocked()
            return dict(self._folder(folder_id))

    def delete(self, fid):
        with self._lock:
            self.entry(fid)
            del self._index["files"][fid]
            self._save_index()
            try:
                os.remove(self._blob_path(fid))
            except FileNotFoundError:
                pass

    def rename(self, fid, new_name):
        new_name = self._clean_name(new_name)
        with self._lock:
            self.entry(fid)
            e = self._index["files"][fid]
            e["name"] = new_name
            e["kind"] = classify(new_name)
            e.pop("thumb", None)  # se recalcula al listar si ahora es una imagen
            e["mime"] = mimetypes.guess_type(new_name)[0] or "application/octet-stream"
            self._save_index()
            return dict(e, id=fid)
