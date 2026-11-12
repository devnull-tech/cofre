"""Funciones que la interfaz QML llama a través de PyOtherSide.

Todas devuelven un diccionario {"ok": True, ...} o
{"ok": False, "error": código, "params": {...}} para que la interfaz nunca reciba
una excepción sin controlar. Los errores son códigos (p. ej. "wrong_password")
que la interfaz traduce al idioma del teléfono.
"""

import errno
import functools
import os
import traceback

try:
    import pyotherside
except ImportError:  # pruebas fuera del teléfono
    pyotherside = None

from cofre.crypto import CryptoError
from cofre.vault import Vault, VaultError, fspath, text
from cofre.media import MediaCache

ORG = "es.sactu"
APP = "cofre"
TEXT_LIMIT = 1024 * 1024
# PyOtherSide registra el proveedor como "python": en QML se usa
# image://python/full/<id> e image://python/thumb/<id>

_vault = None
_media = None
# Originales de la última importación (rutas en bytes), pendientes de que el
# usuario decida si se borran. No se envían a QML para no perder bytes.
_pending = {"paths": [], "root": None}


def _send(*args):
    if pyotherside is not None:
        pyotherside.send(*args)


def _clean(value):
    """Garantiza que nada de lo que va a QML contiene bytes ni caracteres
    sustitutos: PyOtherSide se cae (SIGSEGV) al convertirlos."""
    if isinstance(value, (str, bytes)):
        return text(value)
    if isinstance(value, dict):
        return {_clean(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


_ERRNO_CODES = {errno.ENOENT: "file_not_found", errno.EACCES: "permission_denied",
                errno.EPERM: "permission_denied", errno.ENOSPC: "no_space",
                errno.EROFS: "permission_denied"}


def error_info(e):
    """(código, parámetros) de una excepción, para que la interfaz la traduzca."""
    if isinstance(e, VaultError):
        return e.code, e.params
    if isinstance(e, CryptoError):
        return "corrupt", {}
    if isinstance(e, OSError) and e.errno in _ERRNO_CODES:
        return _ERRNO_CODES[e.errno], {}
    if isinstance(e, OSError):
        return "os_error", {"detail": e.strerror or str(e)}
    traceback.print_exc()
    return "unexpected", {"detail": "%s: %s" % (type(e).__name__, e)}


def _failure(name, e):
    code, params = error_info(e)
    return {"name": name, "error": code, "params": params}


def _api(fn):
    @functools.wraps(fn)
    def wrapper(*args):
        try:
            result = fn(*args) or {}
            result["ok"] = True
        except Exception as e:
            code, params = error_info(e)
            result = {"ok": False, "error": code, "params": params}
        return _clean(result)
    return wrapper


# --- imágenes: proveedor de PyOtherSide, sin red ni ficheros --------------------

_ENCODED = getattr(pyotherside, "format_data", -1)


def image_provider(image_id, requested_size):
    """QML pide image://python/<full|thumb>/<id>; se descifra en memoria.
    Si no se puede (bloqueado, sin miniatura...), devuelve una imagen vacía y el
    Image de QML queda en estado Error, que la interfaz usa para mostrar el icono."""
    try:
        kind, fid = image_id.split("?", 1)[0].split("/", 1)
        if _vault is None or not _vault.unlocked:
            data = b""
        elif kind == "thumb":
            data = _vault.thumbnail(fid) or b""
        else:
            data = _vault.read_bytes(fid)
    except (VaultError, ValueError):
        data = b""  # id inválido o fichero borrado: la interfaz muestra el icono
    except Exception:
        traceback.print_exc()
        data = b""
    return bytearray(data), (-1, -1), _ENCODED


if pyotherside is not None:
    pyotherside.set_image_provider(image_provider)


def _public(entry):
    """Solo lo que la interfaz necesita de cada fichero."""
    return {"id": entry["id"], "name": entry["name"], "size": entry["size"],
            "kind": entry["kind"], "added": entry["added"],
            "thumb": entry.get("thumb", ""), "orientation": entry.get("orientation", 1)}


@_api
def init(data_dir=None, media_dir=None, require_ram=True):
    global _vault, _media
    home = os.path.expanduser("~")
    root = data_dir or os.path.join(home, ".local", "share", ORG, APP)
    _vault = Vault(root)
    if media_dir is None:
        runtime = os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid()
        media_dir = os.path.join(runtime, "cofre-media")
    _media = MediaCache(_vault, media_dir, require_ram)
    _media.clear()
    return {"exists": _vault.exists(), "unlocked": _vault.unlocked}


@_api
def create(password):
    _vault.create(password)


@_api
def unlock(password):
    _vault.unlock(password)


@_api
def lock():
    _pending["paths"], _pending["root"] = [], None
    _media.clear()
    _vault.lock()


# --- vídeo y audio: copia temporal en RAM ----------------------------------------

@_api
def open_media(fid):
    """Empieza a descifrar fid a la RAM privada. El resultado llega como evento:
    ("media-ready", fid, url) o ("media-error", fid, código, parámetros)."""
    def failed(f, e):
        code, params = error_info(e)
        _send("media-error", f, code, _clean(params))
    _media.open_async(fid, lambda f, path: _send("media-ready", f, "file://" + path), failed)


@_api
def close_media(fid=""):
    """Cancela el descifrado y borra la copia. Con fid, solo si es de ese fichero."""
    _media.close(fid or None)


@_api
def change_password(old, new):
    _vault.change_password(old, new)


# --- listado y carpetas -------------------------------------------------------

@_api
def list_files(folder=""):
    return {"folder": folder,
            "path": _vault.folder_path(folder),
            "folders": _vault.folders(folder),
            "files": [_public(e) for e in _vault.list(folder)]}


@_api
def folder_tree(exclude=None):
    """exclude: id o lista de ids de carpetas que no pueden ser destino."""
    return {"folders": _vault.folder_tree(exclude or None)}


@_api
def create_folder(name, parent=""):
    return {"id": _vault.create_folder(name, parent)}


@_api
def rename_folder(folder_id, name):
    _vault.rename_folder(folder_id, name)


@_api
def move_folder(folder_id, parent):
    _vault.move_folder(folder_id, parent)


@_api
def delete_folder(folder_id):
    return {"deleted": _vault.delete_folder(folder_id)}


@_api
def move_file(fid, folder):
    _vault.move_file(fid, folder)


# --- varios elementos a la vez (selección múltiple) ----------------------------
# items: lista de {"type": "file" | "folder", "id": ...}

def _batch(items, action):
    done, failed = 0, []
    for item in items:
        try:
            r = action(item)
            done += 1 if r is None else r
        except Exception as e:
            name = item.get("name") or item.get("id", "?")
            failed.append(_failure(name, e))
    return {"done": done, "failed": failed}


@_api
def move_items(items, dest):
    def move(item):
        if item["type"] == "folder":
            _vault.move_folder(item["id"], dest)
        else:
            _vault.move_file(item["id"], dest)
    return _batch(items, move)


@_api
def delete_items(items):
    """Borra ficheros y carpetas (con su contenido). "done" cuenta elementos."""
    def delete(item):
        if item["type"] == "folder":
            _vault.delete_folder(item["id"])
        else:
            _vault.delete(item["id"])
    return _batch(items, delete)


@_api
def export_items(items):
    """Exporta a Descargas. "done" cuenta ficheros (incluidos los de carpetas)."""
    dest = os.path.join(os.path.expanduser("~"), "Downloads")

    def export(item):
        if item["type"] == "folder":
            return _vault.export_folder(item["id"], dest)[1]
        _vault.export(item["id"], dest)
    result = _batch(items, export)
    result["dest"] = dest
    return result


# --- importación --------------------------------------------------------------

def _import_many(jobs, root=None):
    """jobs: lista de (ruta en bytes, carpeta destino). Informa del progreso por
    bytes y deja los originales importados pendientes de borrar."""
    sizes = []
    for path, _ in jobs:
        try:
            sizes.append(max(1, os.path.getsize(path)))
        except OSError:
            sizes.append(1)
    total_bytes = float(sum(sizes)) or 1.0
    total = len(jobs)
    imported, failed = [], []
    base = 0
    state = {"last": -1.0}

    for i, ((path, folder), size) in enumerate(zip(jobs, sizes)):
        name = text(os.path.basename(path))

        def progress(done, i=i, name=name, base=base, size=size):
            frac = (base + min(done, size)) / total_bytes
            if frac - state["last"] >= 0.005:
                state["last"] = frac
                _send("import-progress", frac, name, i + 1, total)

        progress(0)
        try:
            _vault.import_file(path, progress, folder)
            imported.append(path)
        except Exception as e:
            failed.append(_failure(name, e))
        base += size
    _send("import-progress", 1.0, "", total, total)
    _pending["paths"] = imported
    _pending["root"] = root
    return {"imported": len(imported), "failed": failed, "folder_import": root is not None}


@_api
def import_files(paths, folder=""):
    return _import_many([(fspath(p), folder) for p in paths])


@_api
def import_folder(path, parent=""):
    """Importa una carpeta del teléfono con sus subcarpetas, recreando la estructura.
    Ignora ficheros y carpetas ocultos (los que empiezan por punto).
    Trabaja con rutas en bytes: dentro del sandbox no hay locale UTF-8."""
    path = os.path.abspath(fspath(path))
    if not os.path.isdir(path):
        raise VaultError("not_a_folder")
    root_id = _vault.create_folder(text(os.path.basename(path)) or "Importado", parent)
    folder_ids = {path: root_id}
    jobs = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(b"."))
        current = folder_ids[dirpath]
        for d in dirnames:
            folder_ids[os.path.join(dirpath, d)] = _vault.create_folder(text(d), current)
        for f in sorted(filenames):
            full = os.path.join(dirpath, f)
            if not f.startswith(b".") and os.path.isfile(full) and not os.path.islink(full):
                jobs.append((full, current))
    result = _import_many(jobs, root=path)
    result["folder"] = root_id
    return result


@_api
def delete_originals():
    """Borra los originales de la última importación. Si era una carpeta, quita
    también las subcarpetas que hayan quedado vacías (y la carpeta si queda vacía)."""
    paths, root = _pending["paths"], _pending["root"]
    _pending["paths"], _pending["root"] = [], None
    deleted, failed = 0, []
    for path in paths:
        try:
            os.remove(path)
            deleted += 1
        except OSError as e:
            failed.append(_failure(text(os.path.basename(path)), e))
    if root and os.path.isdir(root):
        for dirpath, _, _ in sorted(os.walk(root), key=lambda w: -len(w[0])):
            try:
                os.rmdir(dirpath)  # solo funciona si está vacía
            except OSError:
                pass
    return {"deleted": deleted, "failed": failed}


@_api
def keep_originals():
    _pending["paths"], _pending["root"] = [], None


# --- ficheros -----------------------------------------------------------------

@_api
def read_text(fid):
    entry = _vault.entry(fid)
    data = _vault.read_bytes(fid, TEXT_LIMIT)
    return {"text": data.decode("utf-8", errors="replace"),
            "truncated": entry["size"] > TEXT_LIMIT}


@_api
def export_file(fid):
    home = os.path.expanduser("~")
    return {"path": _vault.export(fid, os.path.join(home, "Downloads"))}


@_api
def delete_file(fid):
    _vault.delete(fid)


@_api
def rename_file(fid, name):
    _vault.rename(fid, name)
