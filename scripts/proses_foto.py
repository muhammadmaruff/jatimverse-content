#!/usr/bin/env python3
"""Proses foto paket berita Jatimverse.

Mode uji : python scripts/proses_foto.py --uji URL [URL ...]
           Unduh, olah, simpan ke uji/ dan tulis uji/hasil.json (tanpa menyentuh manifest).
Mode paket: python scripts/proses_foto.py
           Olah semua paket di manifest.json berstatus butuh_gambar yang punya url_foto_sumber.
"""
import argparse
import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest.json"
FOTO_DIR = ROOT / "foto"
UJI_DIR = ROOT / "uji"
MAKS_BYTE = 100 * 1024
UA = {"User-Agent": "Mozilla/5.0 (compatible; JatimverseBot/1.0)"}


def unduh(url):
    r = requests.get(url, headers=UA, timeout=45)
    r.raise_for_status()
    return r.content


def olah(data, tujuan):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    target = 16 / 9
    if w / h > target:
        nw = int(h * target)
        kiri = (w - nw) // 2
        img = img.crop((kiri, 0, kiri + nw, h))
    else:
        nh = int(w / target)
        atas = (h - nh) // 2
        img = img.crop((0, atas, w, atas + nh))
    for ukuran in ((1280, 720), (1200, 675)):
        kecil = img.resize(ukuran, Image.LANCZOS)
        for q in range(88, 29, -4):
            buf = io.BytesIO()
            kecil.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
            if buf.tell() <= MAKS_BYTE:
                tujuan.parent.mkdir(parents=True, exist_ok=True)
                tujuan.write_bytes(buf.getvalue())
                return {"ukuran_kb": round(buf.tell() / 1024, 1),
                        "dimensi": f"{ukuran[0]}x{ukuran[1]}", "kualitas": q,
                        "asal": f"{w}x{h}"}
    raise RuntimeError("tidak bisa ≤100 KB")


def mode_uji(urls):
    hasil = []
    for i, url in enumerate(urls, 1):
        item = {"url": url}
        try:
            data = unduh(url)
            item["byte_asli"] = len(data)
            item.update(olah(data, UJI_DIR / f"uji_{i}.jpg"))
            item["status"] = "ok"
        except Exception as e:  # noqa: BLE001
            item["status"] = "gagal"
            item["galat"] = f"{type(e).__name__}: {e}"[:300]
        hasil.append(item)
    UJI_DIR.mkdir(exist_ok=True)
    (UJI_DIR / "hasil.json").write_text(json.dumps(hasil, indent=2, ensure_ascii=False))
    print(json.dumps(hasil, indent=2, ensure_ascii=False))
    return 0 if all(h["status"] == "ok" for h in hasil) else 1


def mode_paket():
    m = json.loads(MANIFEST.read_text())
    ubah = 0
    for p in m.get("paket", []):
        if p.get("status") != "butuh_gambar" or not p.get("url_foto_sumber"):
            continue
        tujuan = FOTO_DIR / f"{p['id']}.jpg"
        try:
            info = olah(unduh(p["url_foto_sumber"]), tujuan)
            p.update(file_jpg=f"foto/{p['id']}.jpg", ukuran_kb=info["ukuran_kb"],
                     dimensi=info["dimensi"])
            # 'lengkap' hanya diberikan oleh scripts/verifikasi.py --tulis
            p["status"] = "draf"
            p["catatan"] = "foto diproses, menunggu verifikasi"
            ubah += 1
        except Exception as e:  # noqa: BLE001
            p["catatan"] = f"foto gagal: {type(e).__name__}: {e}"[:300]
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False))
    print(f"paket diperbarui: {ubah}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--uji", nargs="+")
    a = ap.parse_args()
    sys.exit(mode_uji(a.uji) if a.uji else mode_paket())
