"""Pruebas del núcleo de Cofre. Ejecutar con: python3 -m unittest discover tests"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from cofre import crypto  # noqa: E402
from cofre.vault import Vault, VaultError, WrongPassword  # noqa: E402
import cofre_bridge  # noqa: E402

C = crypto.CHUNK_SIZE
PW = "contraseña-segura"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "vault")
        self.vault = Vault(self.root)
        self.vault.create(PW)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def make_file(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def blob(self, fid):
        return os.path.join(self.root, "blobs", fid + ".cof")


class TestAead(unittest.TestCase):
    """Vectores de prueba de la especificación GCM (McGrew & Viega, casos 13 y 14)."""

    def test_known_answers(self):
        from cofre.aead import AESGCM
        aes = AESGCM(bytes(32))
        self.assertEqual(aes.encrypt(bytes(12), b"", b"").hex(), "530f8afbc74536b9a963b4f1c4cb738b")
        self.assertEqual(aes.encrypt(bytes(12), bytes(16), b"").hex(),
                         "cea7403d4d606b6e074ec5d3baf39d18" "d0d1c8a799996bf0265b98b5d48ab919")

    def test_against_reference(self):
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM as Ref
        except Exception:
            self.skipTest("cryptography no disponible")
        from cofre.aead import AESGCM, InvalidTag
        for size in (0, 1, 15, 16, 17, 1000, C):
            key, nonce, data, aad = os.urandom(32), os.urandom(12), os.urandom(size), os.urandom(size % 40)
            ct = AESGCM(key).encrypt(nonce, data, aad)
            self.assertEqual(ct, Ref(key).encrypt(nonce, data, aad))
            self.assertEqual(AESGCM(key).decrypt(nonce, ct, aad), data)
            with self.assertRaises(InvalidTag):
                AESGCM(key).decrypt(nonce, ct, aad + b"x")


class TestRoundTrip(Base):
    def test_sizes(self):
        for size in (0, 1, C - 1, C, C + 1, 3 * C + 5):
            data = os.urandom(size)
            e = self.vault.import_file(self.make_file("f%d.bin" % size, data))
            self.assertEqual(e["size"], size)
            self.assertEqual(self.vault.read_bytes(e["id"]), data)
            raw = open(self.blob(e["id"]), "rb").read()
            if size > 32:
                self.assertNotIn(data[:32], raw)

    def test_ranges(self):
        data = os.urandom(3 * C + 777)
        e = self.vault.import_file(self.make_file("v.mp4", data))
        with self.vault.open_reader(e["id"]) as r:
            for start, end in ((0, 10), (C - 3, C + 3), (2 * C, 3 * C + 777), (5, 5), (len(data) - 1, len(data) + 50)):
                self.assertEqual(b"".join(r.iter_range(start, end)), data[start:end])

    def test_persistence_and_password(self):
        e = self.vault.import_file(self.make_file("nota.txt", "hola ñandú".encode()))
        v2 = Vault(self.root)
        with self.assertRaises(WrongPassword):
            v2.unlock("otra-contraseña")
        v2.unlock(PW)
        self.assertEqual(v2.list()[0]["name"], "nota.txt")
        v2.change_password(PW, "nueva-contraseña")
        v3 = Vault(self.root)
        with self.assertRaises(WrongPassword):
            v3.unlock(PW)
        v3.unlock("nueva-contraseña")
        self.assertEqual(v3.read_bytes(e["id"]).decode(), "hola ñandú")

    def test_short_password(self):
        with self.assertRaises(VaultError):
            Vault(os.path.join(self.tmp, "otro")).create("corta")

    def test_locked(self):
        self.vault.lock()
        with self.assertRaises(VaultError):
            self.vault.list()

    def test_rename_delete_export(self):
        e = self.vault.import_file(self.make_file("a.txt", b"abc"))
        self.assertEqual(self.vault.rename(e["id"], "b.jpg")["kind"], "image")
        out = os.path.join(self.tmp, "out")
        p1 = self.vault.export(e["id"], out)
        p2 = self.vault.export(e["id"], out)
        self.assertNotEqual(p1, p2)
        self.assertEqual(open(p2, "rb").read(), b"abc")
        self.vault.delete(e["id"])
        self.assertFalse(os.path.exists(self.blob(e["id"])))
        self.assertEqual(self.vault.list(), [])


class TestFolders(Base):
    def test_create_list_move_delete(self):
        fotos = self.vault.create_folder("Fotos")
        viaje = self.vault.create_folder("Viaje", fotos)
        self.assertEqual(self.vault.create_folder("fotos"), self.vault.folders()[1]["id"])
        self.assertEqual([f["name"] for f in self.vault.folders()], ["Fotos", "fotos (2)"])

        a = self.vault.import_file(self.make_file("a.jpg", b"a"), folder=viaje)
        b = self.vault.import_file(self.make_file("b.txt", b"b"))
        self.assertEqual([e["id"] for e in self.vault.list("")], [b["id"]])
        self.assertEqual([e["id"] for e in self.vault.list(viaje)], [a["id"]])
        self.assertEqual(len(self.vault.list()), 2)
        self.assertEqual(self.vault.folders()[0]["count"], 1)  # Fotos contiene Viaje
        self.assertEqual([p["name"] for p in self.vault.folder_path(viaje)], ["Fotos", "Viaje"])

        self.vault.move_file(b["id"], viaje)
        self.assertEqual(len(self.vault.list(viaje)), 2)
        with self.assertRaises(VaultError):
            self.vault.move_folder(fotos, viaje)  # ciclo
        self.assertEqual([f["name"] for f in self.vault.folder_tree(exclude=fotos)], ["fotos (2)"])

        v2 = Vault(self.root)
        v2.unlock(PW)
        self.assertEqual(len(v2.list(viaje)), 2)

        self.assertEqual(self.vault.delete_folder(fotos), 2)
        self.assertEqual(self.vault.list(), [])
        self.assertFalse(os.path.exists(self.blob(a["id"])))
        self.assertEqual([f["name"] for f in self.vault.folders()], ["fotos (2)"])

    def test_upgrade_v1_index(self):
        from cofre import vault as vmod
        e = self.vault.import_file(self.make_file("a.txt", b"a"))
        old = {"version": 1, "files": {e["id"]: {k: v for k, v in self.vault.entry(e["id"]).items()
                                                 if k not in ("id", "folder")}}}
        self.vault._index = old
        self.vault._save_index()
        v2 = Vault(self.root)
        v2.unlock(PW)
        self.assertEqual(v2.list("")[0]["folder"], "")
        self.assertEqual(v2.folders(), [])
        self.assertEqual(vmod.Vault._upgrade(dict(old))["version"], 2)


class TestTampering(Base):
    def setUp(self):
        super().setUp()
        self.data = os.urandom(3 * C + 10)
        self.fid = self.vault.import_file(self.make_file("x.bin", self.data))["id"]
        self.path = self.blob(self.fid)
        self.raw = open(self.path, "rb").read()

    def write(self, raw):
        with open(self.path, "wb") as f:
            f.write(raw)

    def assertRejected(self):
        with self.assertRaises(crypto.CryptoError):
            self.vault.read_bytes(self.fid)

    def test_flip_byte(self):
        raw = bytearray(self.raw)
        raw[crypto.HEADER_LEN + C + 100] ^= 1
        self.write(bytes(raw))
        self.assertRejected()

    def test_truncate_last_chunk(self):
        stride = C + crypto.TAG_LEN
        self.write(self.raw[:crypto.HEADER_LEN + 3 * stride])
        self.assertRejected()

    def test_swap_chunks(self):
        h, s = crypto.HEADER_LEN, C + crypto.TAG_LEN
        c0, c1 = self.raw[h:h + s], self.raw[h + s:h + 2 * s]
        self.write(self.raw[:h] + c1 + c0 + self.raw[h + 2 * s:])
        self.assertRejected()

    def test_blob_swapped_between_files(self):
        other = self.vault.import_file(self.make_file("y.bin", os.urandom(100)))["id"]
        shutil.copy(self.blob(other), self.path)
        self.assertRejected()

    def test_index_tampered(self):
        idx = os.path.join(self.root, "index.bin")
        raw = bytearray(open(idx, "rb").read())
        raw[-1] ^= 1
        open(idx, "wb").write(bytes(raw))
        with self.assertRaises(VaultError):
            Vault(self.root).unlock(PW)


def make_jpeg(thumb=None, orientation=1, big_endian=False, filler=200000):
    """JPEG sintético con bloque EXIF (orientación y, opcionalmente, miniatura)."""
    import struct
    bo = ">" if big_endian else "<"
    tiff = (b"MM" if big_endian else b"II") + struct.pack(bo + "HI", 42, 8)
    ifd0 = struct.pack(bo + "H", 1) + struct.pack(bo + "HHIH2x", 0x0112, 3, 1, orientation)
    if thumb is None:
        tiff += ifd0 + struct.pack(bo + "I", 0)
    else:
        ifd1_off = 8 + len(ifd0) + 4
        thumb_off = ifd1_off + 2 + 2 * 12 + 4
        tiff += ifd0 + struct.pack(bo + "I", ifd1_off)
        tiff += struct.pack(bo + "H", 2) + struct.pack(bo + "HHII", 0x0201, 4, 1, thumb_off)
        tiff += struct.pack(bo + "HHII", 0x0202, 4, 1, len(thumb)) + struct.pack(bo + "I", 0)
        tiff += thumb
    app1 = b"Exif\0\0" + tiff
    return (b"\xff\xd8\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
            + b"\xff\xda" + os.urandom(filler) + b"\xff\xd9")


class TestImageInfo(unittest.TestCase):
    THUMB = b"\xff\xd8miniatura\xff\xd9"

    def test_exif_thumbnail_and_orientation(self):
        from cofre import imageinfo
        for big in (False, True):
            data = make_jpeg(self.THUMB, orientation=6, big_endian=big)
            (start, length), orient = imageinfo.exif_info(data)
            self.assertEqual(data[start:start + length], self.THUMB)
            self.assertEqual(orient, 6)
            self.assertEqual(imageinfo.analyze(data, 5 * 1024 * 1024), ("exif", 6))

    def test_without_thumbnail(self):
        from cofre import imageinfo
        data = make_jpeg(None, orientation=3)
        self.assertEqual(imageinfo.exif_info(data), (None, 3))
        self.assertEqual(imageinfo.analyze(data, 1000), ("full", 3))
        self.assertEqual(imageinfo.analyze(data, 50 * 1024 * 1024), ("", 3))
        self.assertEqual(imageinfo.analyze(b"\x89PNG\r\n", 1000), ("full", 1))

    def test_garbage_does_not_crash(self):
        from cofre import imageinfo
        for _ in range(200):
            junk = b"\xff\xd8\xff\xe1" + os.urandom(300)
            imageinfo.exif_info(junk)
        imageinfo.exif_info(make_jpeg(self.THUMB)[:60])  # truncado


class TestBridge(unittest.TestCase):
    def setUp(self):
        import threading
        self.events = []
        self.cond = threading.Condition()
        self._orig_send = cofre_bridge._send

        def record(*args):
            with self.cond:
                self.events.append(args)
                self.cond.notify_all()
        cofre_bridge._send = record
        self.tmp = tempfile.mkdtemp()
        self.media_dir = os.path.join(self.tmp, "media")
        r = cofre_bridge.init(os.path.join(self.tmp, "v"), self.media_dir, False)
        self.assertTrue(r["ok"], r)
        self.assertTrue(cofre_bridge.create(PW)["ok"])

    def tearDown(self):
        cofre_bridge.lock()
        cofre_bridge._send = self._orig_send
        shutil.rmtree(self.tmp)

    def wait_media(self, fid, timeout=20):
        """Espera el evento media-ready/media-error de fid. Devuelve (tipo, valor)."""
        import time
        deadline = time.time() + timeout
        with self.cond:
            while True:
                for ev in self.events:
                    if ev[0] in ("media-ready", "media-error") and ev[1] == fid:
                        self.events.remove(ev)
                        return ev[0], ev[2]
                left = deadline - time.time()
                self.assertGreater(left, 0, "no llegó el evento de " + fid)
                self.cond.wait(left)

    def media_path(self, fid):
        self.assertTrue(cofre_bridge.open_media(fid)["ok"])
        kind, value = self.wait_media(fid)
        self.assertEqual(kind, "media-ready", value)
        return value[len("file://"):]

    def test_flow(self):
        data = os.urandom(2 * C + 3)
        src = os.path.join(self.tmp, "clip.mp4")
        open(src, "wb").write(data)
        txt = os.path.join(self.tmp, "n.txt")
        open(txt, "wb").write(b"texto")
        r = cofre_bridge.import_files([src, txt, "/no/existe.jpg"])
        self.assertEqual(r["imported"], 2)
        self.assertEqual(len(r["failed"]), 1)

        files = {f["name"]: f for f in cofre_bridge.list_files()["files"]}
        self.assertEqual(cofre_bridge.read_text(files["n.txt"]["id"])["text"], "texto")
        self.assertNotIn("url", files["clip.mp4"])  # ya no hay URLs ni servidor

        # Vídeo: copia temporal idéntica, privada, que se borra al cerrar
        path = self.media_path(files["clip.mp4"]["id"])
        self.assertTrue(path.startswith(self.media_dir) and path.endswith(".mp4"))
        self.assertEqual(open(path, "rb").read(), data)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.media_dir).st_mode & 0o777, 0o700)
        cofre_bridge.close_media()
        self.assertFalse(os.path.exists(path))

        # Abrir otro cierra el anterior; bloquear borra todo
        p1 = self.media_path(files["clip.mp4"]["id"])
        p2 = self.media_path(files["clip.mp4"]["id"])
        self.assertFalse(os.path.exists(p1))
        self.assertTrue(os.path.exists(p2))

        self.assertEqual(cofre_bridge.delete_originals()["deleted"], 2)
        self.assertFalse(os.path.exists(src))
        self.assertEqual(cofre_bridge.delete_originals()["deleted"], 0)  # ya no hay pendientes

        cofre_bridge.lock()
        self.assertEqual(os.listdir(self.media_dir), [])
        cofre_bridge.open_media(files["clip.mp4"]["id"])
        self.assertEqual(self.wait_media(files["clip.mp4"]["id"])[0], "media-error")
        self.assertFalse(cofre_bridge.list_files()["ok"])
        self.assertFalse(cofre_bridge.unlock("mala-contraseña")["ok"])
        self.assertTrue(cofre_bridge.unlock(PW)["ok"])

    def test_leftovers_removed_on_start(self):
        os.makedirs(self.media_dir, exist_ok=True)
        stale = os.path.join(self.media_dir, "resto.mp4")
        open(stale, "wb").write(b"x")
        cofre_bridge.init(os.path.join(self.tmp, "v"), self.media_dir, False)
        self.assertFalse(os.path.exists(stale))

    def test_refuses_media_outside_ram(self):
        from cofre.media import filesystem_type
        disk_dir = tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(__file__)))
        try:
            if filesystem_type(disk_dir) in ("tmpfs", "ramfs"):
                self.skipTest("la carpeta del proyecto está en RAM en este sistema")
            src = os.path.join(self.tmp, "v.mp4")
            open(src, "wb").write(b"video")
            cofre_bridge.import_files([src])
            fid = cofre_bridge.list_files()["files"][0]["id"]
            cofre_bridge.init(os.path.join(self.tmp, "v"), os.path.join(disk_dir, "m"), True)
            cofre_bridge.unlock(PW)
            cofre_bridge.open_media(fid)
            kind, msg = self.wait_media(fid)
            self.assertEqual(kind, "media-error")
            self.assertEqual(msg, "no_secure_memory")
            self.assertEqual(os.listdir(os.path.join(disk_dir, "m")), [])
        finally:
            shutil.rmtree(disk_dir)

    def test_media_skipped_while_decrypting(self):
        """En la galería se pasa de largo un vídeo grande: su descifrado se
        cancela, no deja restos y solo queda la copia del último."""
        big = os.path.join(self.tmp, "grande.mp4")
        with open(big, "wb") as f:
            f.write(os.urandom(40 * 1024 * 1024))
        small = os.path.join(self.tmp, "corto.mp4")
        open(small, "wb").write(b"corto")
        cofre_bridge.import_files([big, small])
        ids = {f["name"]: f["id"] for f in cofre_bridge.list_files()["files"]}
        cofre_bridge.open_media(ids["grande.mp4"])
        cofre_bridge.open_media(ids["corto.mp4"])   # se pasa al siguiente enseguida
        kind, url = self.wait_media(ids["corto.mp4"])
        self.assertEqual(kind, "media-ready")
        import time
        time.sleep(1.5)  # da tiempo al hilo cancelado a terminar
        self.assertEqual(os.listdir(self.media_dir), [os.path.basename(url)])
        self.assertFalse(any(ev[1] == ids["grande.mp4"] for ev in self.events if ev[0] == "media-ready"))

        # close_media de otro fichero no borra la copia actual
        cofre_bridge.close_media(ids["grande.mp4"])
        self.assertTrue(os.path.exists(url[7:]))
        cofre_bridge.close_media(ids["corto.mp4"])
        self.assertEqual(os.listdir(self.media_dir), [])

        # Bloquear mientras se descifra cancela y no deja nada
        cofre_bridge.open_media(ids["grande.mp4"])
        cofre_bridge.lock()
        time.sleep(1.5)
        self.assertEqual(os.listdir(self.media_dir), [])

    def test_batch_operations(self):
        a = os.path.join(self.tmp, "a.txt"); open(a, "wb").write(b"A")
        b = os.path.join(self.tmp, "b.jpg"); open(b, "wb").write(b"B")
        c = os.path.join(self.tmp, "c.txt"); open(c, "wb").write(b"C")
        cofre_bridge.import_files([a, b, c])
        ids = {f["name"]: f["id"] for f in cofre_bridge.list_files()["files"]}
        fotos = cofre_bridge.create_folder("Fotos")["id"]
        sub_id = cofre_bridge.create_folder("Sub", fotos)["id"]
        destino = cofre_bridge.create_folder("Destino")["id"]

        # Mover ficheros y una carpeta a la vez
        items = [{"type": "file", "id": ids["a.txt"]}, {"type": "file", "id": ids["b.jpg"]},
                 {"type": "folder", "id": fotos}]
        r = cofre_bridge.move_items(items, destino)
        self.assertEqual((r["done"], r["failed"]), (3, []))
        dest = cofre_bridge.list_files(destino)
        self.assertEqual(sorted(f["name"] for f in dest["files"]), ["a.txt", "b.jpg"])
        self.assertEqual([f["name"] for f in dest["folders"]], ["Fotos"])
        # Una carpeta no puede ir dentro de sí misma: falla solo ese elemento
        r = cofre_bridge.move_items([{"type": "folder", "id": fotos, "name": "Fotos"},
                                     {"type": "file", "id": ids["c.txt"]}], sub_id)
        self.assertEqual(r["done"], 1)
        self.assertEqual(r["failed"][0]["name"], "Fotos")
        self.assertEqual([f["name"] for f in cofre_bridge.folder_tree([fotos])["folders"]], ["Destino"])

        # Exportar ficheros y carpetas (con estructura)
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            r = cofre_bridge.export_items([{"type": "folder", "id": destino}])
            self.assertEqual((r["done"], r["failed"]), (3, []))
            d = os.path.join(home, "Downloads", "Destino")
            self.assertEqual(open(os.path.join(d, "a.txt"), "rb").read(), b"A")
            self.assertEqual(open(os.path.join(d, "Fotos", "Sub", "c.txt"), "rb").read(), b"C")
            r = cofre_bridge.export_items([{"type": "folder", "id": destino}])
            self.assertTrue(os.path.isdir(os.path.join(home, "Downloads", "Destino (1)")))
        finally:
            if old_home is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = old_home

        # Eliminar varios a la vez (la carpeta con su contenido)
        r = cofre_bridge.delete_items([{"type": "file", "id": ids["a.txt"]},
                                       {"type": "folder", "id": fotos}])
        self.assertEqual((r["done"], r["failed"]), (2, []))
        dest = cofre_bridge.list_files(destino)
        self.assertEqual([f["name"] for f in dest["files"]], ["b.jpg"])
        self.assertEqual(dest["folders"], [])
        self.assertEqual(len(os.listdir(os.path.join(self.tmp, "v", "blobs"))), 1)

    def test_image_provider(self):
        thumb = b"\xff\xd8miniatura\xff\xd9"
        big = os.path.join(self.tmp, "camara.jpg")
        open(big, "wb").write(make_jpeg(thumb, orientation=8, filler=4 * 1024 * 1024))
        small = os.path.join(self.tmp, "dibujo.png")
        png = b"\x89PNG\r\n\x1a\n" + os.urandom(1000)
        open(small, "wb").write(png)
        nothumb = os.path.join(self.tmp, "enorme.jpg")
        open(nothumb, "wb").write(make_jpeg(None, filler=4 * 1024 * 1024))
        cofre_bridge.import_files([big, small, nothumb])
        files = {f["name"]: f for f in cofre_bridge.list_files()["files"]}
        self.assertEqual((files["camara.jpg"]["thumb"], files["camara.jpg"]["orientation"]), ("exif", 8))
        self.assertEqual(files["dibujo.png"]["thumb"], "full")
        self.assertEqual(files["enorme.jpg"]["thumb"], "")

        def provide(kind, name):
            data, size, fmt = cofre_bridge.image_provider("%s/%s" % (kind, files[name]["id"]), (100, 100))
            return bytes(data)

        self.assertEqual(provide("thumb", "camara.jpg"), thumb)
        self.assertEqual(provide("full", "camara.jpg"), open(big, "rb").read())
        self.assertEqual(provide("thumb", "dibujo.png"), png)
        self.assertEqual(provide("thumb", "enorme.jpg"), b"")
        self.assertEqual(bytes(cofre_bridge.image_provider("full/" + "0" * 32, (1, 1))[0]), b"")
        self.assertEqual(bytes(cofre_bridge.image_provider("basura", (1, 1))[0]), b"")
        cofre_bridge.lock()
        self.assertEqual(provide("full", "camara.jpg"), b"")

    def test_image_info_for_old_entries(self):
        thumb = b"\xff\xd8mini\xff\xd9"
        src = os.path.join(self.tmp, "vieja.jpg")
        open(src, "wb").write(make_jpeg(thumb, orientation=6))
        cofre_bridge.import_files([src])
        v = cofre_bridge._vault
        fid = v.list("")[0]["id"]
        for key in ("thumb", "orientation"):  # como si se hubiera importado con la versión anterior
            v._index["files"][fid].pop(key)
        f = cofre_bridge.list_files()["files"][0]
        self.assertEqual((f["thumb"], f["orientation"]), ("exif", 6))
        self.assertEqual(v._index["files"][fid]["thumb"], "exif")


    def test_import_folder(self):
        src = os.path.join(self.tmp, "Camara")
        os.makedirs(os.path.join(src, "2026", "Verano"))
        os.makedirs(os.path.join(src, ".thumbnails"))
        files = {"f1.jpg": b"1", "2026/f2.jpg": b"22", "2026/Verano/f3.mp4": b"333",
                 ".oculto": b"x", ".thumbnails/t.png": b"t"}
        for rel, data in files.items():
            with open(os.path.join(src, rel), "wb") as f:
                f.write(data)

        r = cofre_bridge.import_folder(src)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["imported"], 3)
        self.assertTrue(r["folder_import"])
        root = cofre_bridge.list_files()
        self.assertEqual([f["name"] for f in root["folders"]], ["Camara"])
        cam = cofre_bridge.list_files(r["folder"])
        self.assertEqual([f["name"] for f in cam["files"]], ["f1.jpg"])
        self.assertEqual([f["name"] for f in cam["folders"]], ["2026"])
        y = cofre_bridge.list_files(cam["folders"][0]["id"])
        verano = cofre_bridge.list_files(y["folders"][0]["id"])
        self.assertEqual([p["name"] for p in verano["path"]], ["Camara", "2026", "Verano"])
        self.assertEqual(verano["files"][0]["name"], "f3.mp4")

        # Importar otra vez la misma carpeta crea "Camara (2)"
        self.assertTrue(cofre_bridge.import_folder(src)["ok"])
        self.assertEqual([f["name"] for f in cofre_bridge.list_files()["folders"]], ["Camara", "Camara (2)"])

        d = cofre_bridge.delete_originals()
        self.assertEqual(d["deleted"], 3)
        # Quedan solo los ocultos y sus carpetas; las vacías se han eliminado
        self.assertFalse(os.path.exists(os.path.join(src, "2026")))
        self.assertTrue(os.path.exists(os.path.join(src, ".oculto")))


SANDBOX_SCRIPT = r"""# -*- coding: utf-8 -*-
import json, os, sys, tempfile
sys.path.insert(0, sys.argv[1])
import cofre_bridge as b
tmp = tempfile.mkdtemp().encode()
src = os.path.join(tmp, "Vacaciones".encode())
for rel, data in (("Montaña/ñandú.png", b"png"), ("Café €/notas ü.txt", "hola ñ".encode()), ("raíz.jpg", b"j")):
    full = os.path.join(src, rel.encode("utf-8"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "wb").write(data)
out = {"fsenc": sys.getfilesystemencoding()}
b.init(os.path.join(tmp, b"v").decode("ascii"))
b.create("contraseña-segura")
out["import"] = b.import_folder(os.fsdecode(src))
top = b.list_files(out["import"]["folder"])
out["folders"] = [f["name"] for f in top["folders"]]
out["files"] = [f["name"] for f in top["files"]]
cafe = [f for f in top["folders"] if f["name"].startswith("Caf")][0]
inner = b.list_files(cafe["id"])
out["text"] = b.read_text(inner["files"][0]["id"])["text"]
out["rename"] = b.create_folder(os.fsdecode(b"Pel\xc3\xadculas"))["ok"]
os.environ["HOME"] = tmp.decode("ascii")
exp = b.export_file(inner["files"][0]["id"])
out["export"] = exp
out["export_exists"] = os.path.exists(os.path.join(tmp, b"Downloads", "notas ü.txt".encode()))
out["delete"] = b.delete_originals()
out["left"] = sorted(x.decode("utf-8") for x in os.listdir(tmp))
out["src_exists"] = os.path.exists(src)
b.lock()
out["reopen"] = b.unlock("contraseña-segura")["ok"] and [f["name"] for f in b.list_files("")["folders"]]
print(json.dumps(out, ensure_ascii=True))
"""


class TestSandboxLocale(unittest.TestCase):
    """En el sandbox de Sailfish no hay locale UTF-8: Python usa ASCII para los
    nombres de fichero. Este caso hizo caer la app con carpetas como "Montaña"."""

    def test_non_ascii_names_without_utf8_locale(self):
        import json
        import subprocess
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C",
               "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0", "HOME": "/nonexistent"}
        pydir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python")
        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "sandbox_case.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write(SANDBOX_SCRIPT)
            proc = subprocess.run([sys.executable, script, pydir], env=env,
                                  capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        if out["fsenc"].lower().replace("-", "") == "utf8":
            self.skipTest("este Python usa UTF-8 incluso con LC_ALL=C")
        self.assertTrue(out["import"]["ok"], out)
        self.assertEqual(out["import"]["imported"], 3)
        self.assertEqual(out["folders"], ["Café €", "Montaña"])
        self.assertEqual(out["files"], ["raíz.jpg"])
        self.assertEqual(out["text"], "hola ñ")
        self.assertTrue(out["rename"])
        self.assertTrue(out["export"]["ok"], out["export"])
        self.assertTrue(out["export"]["path"].endswith("notas ü.txt"))
        self.assertTrue(out["export_exists"])
        self.assertEqual(out["delete"]["deleted"], 3)
        self.assertFalse(out["src_exists"])
        self.assertEqual(out["reopen"], ["Películas", "Vacaciones"])


if __name__ == "__main__":
    unittest.main()
