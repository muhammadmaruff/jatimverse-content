#!/usr/bin/env python3
"""Unggah paket 'lengkap' ke WordPress via REST API.

Kredensial hanya dari env: WP_URL, WP_USER, WP_APP_PASSWORD.
Pemakaian: python scripts/upload_wp.py [--kering] [--maks N]
Jika config/wordpress.json "aktif" = false, otomatis berjalan sebagai --kering.
"""
import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest.json"
CONFIG = ROOT / "config" / "wordpress.json"
WIB = timezone(timedelta(hours=7))
UA = {"User-Agent": "Mozilla/5.0 (compatible; JatimverseBot/1.0)"}


def slugify(teks):
    s = re.sub(r"[^a-z0-9]+", "-", teks.lower()).strip("-")
    return s[:80].strip("-")


def parse_md(path):
    baris = path.read_text().splitlines()
    judul = baris[0].lstrip("# ").strip()
    paragraf = [b.strip() for b in baris[1:] if b.strip()]
    return judul, paragraf


def ke_html(paragraf):
    out = []
    for p in paragraf:
        if p.startswith("Sumber:"):
            out.append(f"<p><em>{html.escape(p)}</em></p>")
        else:
            out.append(f"<p>{html.escape(p)}</p>")
    return "\n".join(out)


def ringkas(paragraf, n=160):
    teks = next((p for p in paragraf if not p.startswith("Sumber:")), "")
    if len(teks) <= n:
        return teks
    return teks[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


class WP:
    def __init__(self, base, user, pw, jeda):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.auth = (user, pw)
        self.s.headers.update(UA)
        self.jeda = jeda

    def req(self, metode, jalur, **kw):
        url = f"{self.base}/wp-json{jalur}"
        for percobaan in range(3):
            r = self.s.request(metode, url, timeout=60, **kw)
            if r.status_code in (429,) or r.status_code >= 500:
                if percobaan < 2:
                    time.sleep(2 * (percobaan + 1))
                    continue
            return r
        return r

    def jeda_ok(self):
        time.sleep(self.jeda)

    def term(self, taksonomi, slug, nama):
        r = self.req("GET", f"/wp/v2/{taksonomi}", params={"slug": slug})
        if r.ok and r.json():
            return r.json()[0]["id"]
        r = self.req("POST", f"/wp/v2/{taksonomi}", json={"name": nama, "slug": slug})
        if r.ok:
            return r.json()["id"]
        # term_exists mengembalikan id di data
        try:
            return r.json()["data"]["term_id"]
        except Exception:  # noqa: BLE001
            raise RuntimeError(f"{taksonomi} '{slug}' gagal: HTTP {r.status_code}")


def nama_tag(cfg, p):
    """Tag wajib: default + wilayah + kabupaten/kota + tag tambahan paket (bila ada)."""
    kandidat = [t.replace("-", " ").title() for t in cfg.get("tag_default", [])]
    kandidat += [p.get("wilayah", ""), p.get("kabkota", "")] + list(p.get("tag", []))
    hasil, lihat = [], set()
    for n in kandidat:
        n = (n or "").strip()
        if n and slugify(n) not in lihat:
            lihat.add(slugify(n))
            hasil.append(n)
    return hasil


def id_taksonomi(wp, cfg, p):
    kslug = cfg["kategori_per_wilayah"].get(p["wilayah"]) or slugify(p["wilayah"])
    kat = wp.term("categories", kslug, p["wilayah"])
    tags = [wp.term("tags", slugify(n), n) for n in nama_tag(cfg, p)]
    if not kat or not tags:
        raise RuntimeError("kategori/tag kosong")
    return kat, tags


def sinkron_taksonomi(wp, cfg, p):
    """Lengkapi kategori dan tag pada post buatan pipeline (hanya menambah, tidak menghapus)."""
    r = wp.req("GET", f"/wp/v2/posts/{p['wp_post_id']}", params={"context": "edit"})
    if not r.ok:
        raise RuntimeError(f"GET post HTTP {r.status_code}")
    v = r.json()
    kat, tags = id_taksonomi(wp, cfg, p)
    k_lama, t_lama = set(v.get("categories", [])), set(v.get("tags", []))
    k_baru, t_baru = k_lama | {kat}, t_lama | set(tags)
    if k_baru == k_lama and t_baru == t_lama:
        return "taksonomi sudah lengkap"
    r = wp.req("POST", f"/wp/v2/posts/{p['wp_post_id']}",
               json={"categories": sorted(k_baru), "tags": sorted(t_baru)})
    if not r.ok:
        raise RuntimeError(f"update taksonomi HTTP {r.status_code}")
    j = r.json()
    if kat not in j.get("categories", []) or not set(tags) <= set(j.get("tags", [])):
        raise RuntimeError("verifikasi taksonomi gagal")
    p["catatan_wp"] = ""
    return f"taksonomi dilengkapi: kategori {sorted(k_baru)}, tag {sorted(t_baru)}"


def uji_koneksi(wp):
    try:
        r = wp.req("GET", "/")
    except requests.RequestException as e:
        sys.exit(f"KONEKSI GAGAL: {type(e).__name__}: {e}"[:300])
    if r.status_code in (403, 406) or "text/html" in r.headers.get("content-type", ""):
        sys.exit(f"WP-JSON DIBLOKIR (HTTP {r.status_code}); kemungkinan WAF/keamanan menolak IP GitHub Actions.")
    if not r.ok:
        sys.exit(f"wp-json tidak dapat diakses: HTTP {r.status_code}")
    r = wp.req("GET", "/wp/v2/users/me", params={"context": "edit"})
    if r.status_code in (401, 403):
        sys.exit(f"AUTENTIKASI DITOLAK (HTTP {r.status_code}): periksa WP_USER/WP_APP_PASSWORD dan hak akses pengguna.")
    if not r.ok:
        sys.exit(f"users/me gagal: HTTP {r.status_code}")
    print("koneksi WordPress OK")


def unggah_paket(wp, cfg, p):
    judul, paragraf = parse_md(ROOT / p["file_md"])
    slug = slugify(judul)
    r = wp.req("GET", "/wp/v2/posts", params={"slug": slug, "status": "any"})
    if r.ok and r.json():
        ada = r.json()[0]
        p.update(wp_post_id=ada["id"], wp_url=ada.get("link"), status_wp=ada.get("status"),
                 catatan_wp="sudah ada di WordPress; dilewati")
        return "sudah ada"
    # foto
    jpg = ROOT / p["file_jpg"]
    r = wp.req("POST", "/wp/v2/media", data=jpg.read_bytes(),
               headers={"Content-Disposition": f'attachment; filename="{jpg.name}"',
                        "Content-Type": "image/jpeg"})
    if not r.ok:
        raise RuntimeError(f"unggah foto HTTP {r.status_code}")
    media_id = r.json()["id"]
    p["wp_media_id"] = media_id
    wp.req("POST", f"/wp/v2/media/{media_id}",
           json={"alt_text": judul, "caption": f"Foto: {p.get('kredit_foto', '')}"})
    # kategori & tag (wajib terisi)
    kat, tags = id_taksonomi(wp, cfg, p)
    data = {"title": judul, "content": ke_html(paragraf), "excerpt": ringkas(paragraf),
            "slug": slug, "status": cfg["status_wp"], "featured_media": media_id,
            "categories": [kat], "tags": tags}
    if cfg.get("penulis_id"):
        data["author"] = cfg["penulis_id"]
    r = wp.req("POST", "/wp/v2/posts", json=data)
    if not r.ok:
        raise RuntimeError(f"buat post HTTP {r.status_code}")
    post = r.json()
    # verifikasi
    v = wp.req("GET", f"/wp/v2/posts/{post['id']}", params={"context": "edit"})
    if not v.ok:
        raise RuntimeError(f"verifikasi GET HTTP {v.status_code}")
    vj = v.json()
    ex = (vj.get("excerpt") or {}).get("raw", "")
    if (vj.get("featured_media") != media_id or kat not in vj.get("categories", [])
            or not set(tags) <= set(vj.get("tags", [])) or not ex.strip()):
        raise RuntimeError("verifikasi: featured_media/kategori/tag/excerpt tidak sesuai")
    p.update(wp_post_id=vj["id"], wp_url=vj.get("link"), status_wp=vj.get("status"),
             tgl_upload=datetime.now(WIB).isoformat(timespec="seconds"), catatan_wp="")
    return "dibuat"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kering", action="store_true")
    ap.add_argument("--maks", type=int)
    a = ap.parse_args()
    cfg = json.loads(CONFIG.read_text())
    m = json.loads(MANIFEST.read_text())
    maks = a.maks or cfg["maks_per_jalan"]
    kering = a.kering or not cfg.get("aktif", False)
    if kering and not a.kering:
        print('config aktif=false -> mode kering')
    antrean = [p for p in m["paket"] if p.get("status") == "lengkap" and not p.get("wp_post_id")][:maks]
    print(f"paket lengkap belum diunggah (maks {maks}): {len(antrean)}")
    if kering:
        for p in antrean:
            judul, paragraf = parse_md(ROOT / p["file_md"])
            print(f"[KERING] {p['id']} | {p['wilayah']} -> {cfg['kategori_per_wilayah'].get(p['wilayah'])} "
                  f"| tag={nama_tag(cfg, p)} | status={cfg['status_wp']} | slug={slugify(judul)} | foto={p['file_jpg']} ({p.get('ukuran_kb')} KB)")
        base = os.environ.get("WP_URL")
        if base and os.environ.get("WP_USER") and os.environ.get("WP_APP_PASSWORD"):
            uji_koneksi(WP(base, os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"], cfg["jeda_detik"]))
        else:
            print("secret WP_URL/WP_USER/WP_APP_PASSWORD tidak tersedia di env; uji koneksi dilewati")
        return 0
    base, user, pw = (os.environ.get(k) for k in ("WP_URL", "WP_USER", "WP_APP_PASSWORD"))
    if not (base and user and pw):
        sys.exit("Secret WP_URL/WP_USER/WP_APP_PASSWORD belum lengkap; unggah dihentikan.")
    wp = WP(base, user, pw, cfg["jeda_detik"])
    uji_koneksi(wp)
    ok = 0
    for p in antrean:
        try:
            print(f"{p['id']}: {unggah_paket(wp, cfg, p)}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            p["catatan_wp"] = f"{type(e).__name__}: {e}"[:300]
            print(f"{p['id']}: GAGAL {p['catatan_wp']}")
        MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False))
        wp.jeda_ok()
    print(f"selesai: {ok}/{len(antrean)} berhasil")
    for p in m["paket"]:
        if p.get("status") == "lengkap" and p.get("wp_post_id") and p.get("wp_media_id"):
            try:
                print(f"{p['id']}: {sinkron_taksonomi(wp, cfg, p)}")
            except Exception as e:  # noqa: BLE001
                p["catatan_wp"] = f"{type(e).__name__}: {e}"[:300]
                print(f"{p['id']}: GAGAL taksonomi {p['catatan_wp']}")
            MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False))
            wp.jeda_ok()
    return 0


if __name__ == "__main__":
    sys.exit(main())
