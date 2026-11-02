#!/usr/bin/env python3
"""Verifikasi paket sesuai bagian 11 workflow. Hanya paket yang lolos semua syarat dinaikkan ke 'lengkap'.

Pemakaian: python scripts/verifikasi.py [--sekarang "2026-11-03T09:00"] [--tulis]
  --sekarang : waktu mulai eksekusi (WIB) untuk cek rentang. Default: waktu sistem (WIB).
  --tulis    : simpan status baru ke manifest.json (lolos -> lengkap, gagal -> draf/butuh_gambar).
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WIB = timezone(timedelta(hours=7))


def baca_aturan():
    return json.loads((ROOT / "config" / "sumber.json").read_text())["aturan"]


def hitung_kata(path):
    baris = path.read_text().splitlines()
    isi = [b for b in baris[1:] if b.strip() and not b.startswith("Sumber:")]
    return len(re.findall(r"\S+", " ".join(isi))), isi, baris


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sekarang")
    ap.add_argument("--tulis", action="store_true")
    a = ap.parse_args()
    now = datetime.fromisoformat(a.sekarang).replace(tzinfo=WIB) if a.sekarang else datetime.now(WIB)
    aturan = baca_aturan()
    m = json.loads((ROOT / "manifest.json").read_text())
    foto_hash, judul_set, url_set = {}, set(), set()
    gagal_total = 0
    for p in m["paket"]:
        g = []
        peringatan = []
        # metadata editorial wajib
        KAT = {"politik", "ekonomi", "jelajah", "viral", "bola"}
        RUB = {"biar-paham", "cuan-jatim", "derbi-jatim", "jelajah-jatim", "suara-arek", "wakil-kita"}
        for kolom in ("wilayah", "kabkota"):
            if not str(p.get(kolom) or "").strip():
                g.append(f"{kolom} kosong")
        if p.get("kategori") not in KAT:
            g.append("kategori tidak valid")
        if p.get("rubrik") not in RUB:
            g.append("rubrik tidak valid")
        if len(p.get("tag") or []) < 2:
            g.append("tag < 2")
        peta = {}
        cfg = ROOT / "config" / "wordpress.json"
        if cfg.exists():
            peta = json.loads(cfg.read_text()).get("dapil_per_kabkota", {})
        if not (str(p.get("dapil") or "").strip() or peta.get(p.get("kabkota"))):
            g.append("dapil tidak terpetakan")
        md = ROOT / (p.get("file_md") or "tidak-ada")
        jp = ROOT / (p.get("file_jpg") or "tidak-ada")
        if p.get("status") == "lengkap":
            # Paket lengkap tidak disentuh lagi; hanya dicatat agar duplikat terdeteksi.
            if jp.exists():
                foto_hash[hashlib.md5(jp.read_bytes()).hexdigest()] = p["id"]
            judul_set.add(p["judul"])
            url_set.update(p.get("url_sumber", []))
            p["_gagal"] = []
            p["_lewati"] = True
            print(f"{p['id'][-34:]:34} LEWATI (sudah lengkap)")
            continue
        if not md.exists():
            g.append("md hilang")
        else:
            n, isi, baris = hitung_kata(md)
            if n != p.get("jumlah_kata"):
                g.append(f"jumlah_kata manifest {p.get('jumlah_kata')} != {n}")
            if n < aturan["ambang_kata"]:
                peringatan.append(f"kata {n} < {aturan['ambang_kata']} (tetap ditayangkan)")
            if not re.match(r"^[A-Z ,.'/-]+ – ", isi[0]):
                g.append("dateline")
            if len(baris[0].lstrip("# ")) > 75:
                g.append("judul > ~70 karakter")
        if not jp.exists():
            g.append("jpg hilang")
        else:
            kb = jp.stat().st_size / 1024
            im = Image.open(jp)
            if kb > aturan["foto_maks_kb"]:
                g.append(f"foto {kb:.1f} KB")
            if abs(im.size[0] / im.size[1] - 16 / 9) > 0.01:
                g.append("rasio bukan 16:9")
            if p.get("dimensi") != f"{im.size[0]}x{im.size[1]}" or abs((p.get("ukuran_kb") or 0) - kb) > 0.2:
                g.append("manifest != file foto")
            h = hashlib.md5(jp.read_bytes()).hexdigest()
            if h in foto_hash:
                g.append(f"foto ganda dengan {foto_hash[h]}")
            foto_hash[h] = p["id"]
        # rentang waktu
        try:
            tgl = datetime.fromisoformat(p["tgl_terbit_sumber"]).replace(tzinfo=WIB)
            batas = p.get("rentang_jam_khusus") or (48 if p.get("tanda_48j") else aturan["rentang_jam_hari_kerja"])
            if tgl.date() < (now - timedelta(hours=batas)).date():
                g.append("di luar rentang waktu")
        except Exception:
            g.append("tgl_terbit_sumber tidak valid")
        if p["judul"] in judul_set:
            g.append("judul ganda")
        judul_set.add(p["judul"])
        for u in p.get("url_sumber", []):
            if not re.search(r"\.go\.id", u):
                g.append("sumber bukan .go.id")
            if u in url_set:
                g.append("url sumber ganda")
            url_set.add(u)
        p["_gagal"] = g
        p["_peringatan"] = peringatan
        print(f"{p['id'][-34:]:34} {'LOLOS' if not g else 'GAGAL: ' + '; '.join(g)}")
        gagal_total += bool(g)
    if a.tulis:
        for p in m["paket"]:
            g = p.pop("_gagal")
            w = p.pop("_peringatan", [])
            if p.pop("_lewati", False):
                continue
            if not g:
                p["status"] = "lengkap"
                p["catatan"] = "; ".join(w)[:300]
            else:
                p["status"] = "draf" if p.get("file_jpg") else "butuh_gambar"
                p["catatan"] = "; ".join(g)[:300]
        (ROOT / "manifest.json").write_text(json.dumps(m, indent=2, ensure_ascii=False))
    total = len(m["paket"])
    print(f"lolos {total - gagal_total}/{total} paket")
    if a.tulis:
        return 0  # kegagalan dicatat di manifest, tidak menggagalkan workflow
    return 0 if not gagal_total else 1


if __name__ == "__main__":
    sys.exit(main())
