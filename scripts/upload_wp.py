#!/usr/bin/env python3
"""Unggah paket 'lengkap' ke WordPress via REST API.

Kredensial hanya dari env: WP_URL, WP_USER, WP_APP_PASSWORD.
Pemakaian: python scripts/upload_wp.py [--kering] [--maks N] [--sinkron-semua]
Sinkron metadata hanya untuk paket yang perlu (lihat perlu_sinkron); --sinkron-semua memaksa semua.
Jika config/wordpress.json "aktif" = false, otomatis berjalan sebagai --kering.
"""
import argparse
import hashlib
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


SINGKATAN = {"dr", "drs", "ir", "prof", "h", "hj", "kh", "no", "rp", "kec", "kab", "jl", "dsb", "dll",
             "dkk", "tn", "ny", "st", "mr", "sdr", "pt", "cv", "ud", "apt", "drg", "kol", "bpk", "ak",
             "abd", "gg", "ds", "kel", "kota", "ps", "tgl", "hlm", "dst", "yth", "spd", "mpd", "se",
             "msi", "sh", "mh", "st", "mt", "mm", "mag", "skom", "ssos", "sip", "ssi", "sag", "mhum"}
BATAS_KALIMAT = re.compile(r'[.!?]+["\u201d)\]]*\s+(?=["\u201c(\[]?[A-Z0-9])')


def pecah_kalimat(teks):
    """Pecah paragraf menjadi kalimat; tidak memecah di dalam tanda kutip, singkatan, atau inisial."""
    hasil, awal = [], 0
    for mt in BATAS_KALIMAT.finditer(teks):
        sebelum = teks[awal:mt.start()]
        penutup = mt.group(0)
        # status kutip pada titik tanda baca
        buka_lengkung = teks[:mt.start()].count("\u201c") - teks[:mt.start()].count("\u201d")
        lurus = teks[:mt.start()].count('"') % 2 == 1
        menutup = ('"' in penutup) or ("\u201d" in penutup)
        if (buka_lengkung > 0 or lurus) and not menutup:
            continue
        kata = re.search(r"(\S+)$", teks[:mt.start()])
        kata = kata.group(1) if kata else ""
        bersih = re.sub(r"[^A-Za-z.]", "", kata)
        if penutup.startswith("."):
            inti = bersih.rstrip(".").lower().replace(".", "")
            if inti in SINGKATAN or (len(inti) == 1 and inti.isalpha()) or re.fullmatch(r"\d+", kata.strip("()\"\u201c\u201d")):
                continue
        hasil.append(teks[awal:mt.end()].strip())
        awal = mt.end()
    sisa = teks[awal:].strip()
    if sisa:
        hasil.append(sisa)
    return hasil


def ke_html(paragraf):
    """Satu <p> berisi 1-2 kalimat; baris 'Sumber:' tidak ditayangkan."""
    out = []
    for p in paragraf:
        if p.startswith("Sumber:"):
            continue
        if p.startswith("## "):
            out.append(f"<h2>{html.escape(p[3:].strip())}</h2>")
            continue
        k = pecah_kalimat(p)
        i = 0
        while i < len(k):
            potong = k[i:i + 2]
            if len(potong) == 2 and len(potong[0]) + len(potong[1]) > 420:
                potong = potong[:1]
            out.append(f"<p>{html.escape(' '.join(potong))}</p>")
            i += len(potong)
    return "\n".join(out)


def ringkas(paragraf, n=160):
    teks = next((p for p in paragraf if not p.startswith(("Sumber:", "Oleh:", "## ")) and len(p) > 60), "")
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
        self._term = {}  # cache id term per jalan: (taksonomi, slug) -> id / None

    def req(self, metode, jalur, **kw):
        url = f"{self.base}/wp-json{jalur}"
        for percobaan in range(3):
            try:
                r = self.s.request(metode, url, timeout=60, **kw)
            except (requests.ConnectionError, requests.Timeout):
                if percobaan < 2:
                    time.sleep(5 * (percobaan + 1))
                    continue
                raise
            if r.status_code in (429,) or r.status_code >= 500:
                if percobaan < 2:
                    time.sleep(2 * (percobaan + 1))
                    continue
            return r
        return r

    def jeda_ok(self):
        time.sleep(self.jeda)

    def cari_term(self, taksonomi, slug):
        """Id term berdasarkan slug, atau None. Di-cache: kategori/wilayah/rubrik/dapil/tag
        yang sama dipakai puluhan post, jadi cukup satu request per slug per jalan."""
        kunci = (taksonomi, slug)
        if kunci not in self._term:
            r = self.req("GET", f"/wp/v2/{taksonomi}", params={"slug": slug})
            if not r.ok:
                return None  # galat sementara tidak di-cache
            self._term[kunci] = r.json()[0]["id"] if r.json() else None
        return self._term[kunci]

    def term(self, taksonomi, slug, nama):
        ada = self.cari_term(taksonomi, slug)
        if ada:
            return ada
        r = self.req("POST", f"/wp/v2/{taksonomi}", json={"name": nama, "slug": slug})
        if r.ok:
            tid = r.json()["id"]
        else:
            # term_exists mengembalikan id di data
            try:
                tid = r.json()["data"]["term_id"]
            except Exception:  # noqa: BLE001
                raise RuntimeError(f"{taksonomi} '{slug}' gagal: HTTP {r.status_code}")
        self._term[(taksonomi, slug)] = tid
        return tid


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


def id_meta(wp, cfg, p, wajib=False):
    """Kategori, wilayah, rubrik, dapil (term yang sudah ada di situs) + tag (dibuat bila belum ada)."""
    ids, kurang = {}, []

    def cari(rest, slug, label):
        if not slug:
            kurang.append(f"{label} belum diisi")
            return
        tid = wp.cari_term(rest, slug)
        if tid:
            ids[rest] = [tid]
        else:
            kurang.append(f"{label} '{slug}' tidak ada di WordPress")

    cari("categories", p.get("kategori"), "kategori")
    cari("wilayah", (cfg.get("slug_wilayah") or {}).get(p.get("wilayah")), "wilayah")
    cari("rubrik", p.get("rubrik"), "rubrik")
    cari("dapil", p.get("dapil") or (cfg.get("dapil_per_kabkota") or {}).get(p.get("kabkota")), "dapil")
    ids["tags"] = [wp.term("tags", slugify(n), n) for n in nama_tag(cfg, p)]
    if len(ids["tags"]) < 2:
        kurang.append("tag kurang dari 2")
    if wajib and kurang:
        raise RuntimeError("metadata belum lengkap: " + "; ".join(kurang))
    return ids, kurang


def sinkron_meta(wp, cfg, p, tayang=None):
    """Lengkapi metadata post buatan pipeline: kategori diganti, tag/wilayah/rubrik/dapil hanya ditambah,
    baris Sumber dibuang dari isi."""
    r = wp.req("GET", f"/wp/v2/posts/{p['wp_post_id']}", params={"context": "edit"})
    if not r.ok:
        raise RuntimeError(f"GET post HTTP {r.status_code}")
    v = r.json()
    ids, kurang = id_meta(wp, cfg, p)
    upd = {}
    if ids.get("categories") and sorted(v.get("categories", [])) != sorted(ids["categories"]):
        upd["categories"] = ids["categories"]
    for kunci in ("tags", "wilayah", "rubrik", "dapil"):
        if ids.get(kunci):
            lama = set(v.get(kunci, []))
            if lama | set(ids[kunci]) != lama:
                upd[kunci] = sorted(lama | set(ids[kunci]))
    isi_baru = ke_html(parse_md(ROOT / p["file_md"])[1])
    if (v.get("content") or {}).get("raw", "") != isi_baru:
        upd["content"] = isi_baru
    if p.get("tayang_segera") and v.get("status") == "future":
        upd["status"] = "publish"
        upd["date_gmt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    ulang = bool(p.get("jadwal_ulang") and tayang and v.get("status") == "publish")
    if ulang:
        upd["status"] = "future"
        upd["date_gmt"] = tayang.strftime("%Y-%m-%dT%H:%M:%S")
    if upd:
        r = wp.req("POST", f"/wp/v2/posts/{p['wp_post_id']}", json=upd)
        if not r.ok:
            raise RuntimeError(f"update metadata HTTP {r.status_code}")
        if ulang:
            if r.json().get("status") != "future":
                raise RuntimeError(f"jadwal ulang gagal: status {r.json().get('status')}")
            p.update(status_wp="future", tgl_tayang=tayang.astimezone(WIB).isoformat(timespec="minutes"))
            p.pop("jadwal_ulang", None)
        elif "status" in upd:
            if r.json().get("status") != "publish":
                raise RuntimeError(f"tayang segera gagal: status {r.json().get('status')}")
            p.update(status_wp="publish", tgl_tayang=datetime.now(WIB).isoformat(timespec="minutes"))
            p.pop("tayang_segera", None)
    p["catatan_wp"] = ("metadata kurang: " + "; ".join(kurang)) if kurang else ""
    return f"diperbarui {sorted(upd)}" if upd else "metadata sudah sesuai"


def sidik_meta(cfg, p):
    """Sidik isi + metadata paket. Berubah jika file artikel, metadata manifest, atau config terkait berubah."""
    try:
        isi = (ROOT / p["file_md"]).read_text(encoding="utf-8")
    except OSError:
        isi = ""
    meta = {k: p.get(k) for k in ("judul", "kategori", "rubrik", "tag", "wilayah", "kabkota", "dapil")}
    conf = {k: cfg.get(k) for k in ("tag_default", "slug_wilayah", "dapil_per_kabkota")}
    data = json.dumps([isi, meta, conf], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(data.encode("utf-8")).hexdigest()


def perlu_sinkron(cfg, p, semua=False):
    """Hemat menit Actions: post lama yang tidak berubah tidak perlu dicek ulang setiap jalan."""
    if semua or p.get("jadwal_ulang") or p.get("tayang_segera") or p.get("catatan_wp"):
        return True
    if p.get("sidik_meta") != sidik_meta(cfg, p):
        return True
    hari = cfg.get("hari_sinkron_meta", 3)
    try:
        upload = datetime.fromisoformat(p.get("tgl_upload", ""))
        if upload.tzinfo is None:
            upload = upload.replace(tzinfo=WIB)
    except ValueError:
        return False
    return datetime.now(WIB) - upload <= timedelta(days=hari)


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


def slot_pertama(wp, cfg):
    """Slot tayang pertama (UTC) dan selang antar-post. Lanjut setelah post terjadwal terakhir di situs."""
    j = cfg.get("jadwal_tayang") or {}
    iv = timedelta(minutes=j.get("interval_menit", 45))
    mulai = datetime.now(timezone.utc) + timedelta(minutes=j.get("jeda_awal_menit", 45))
    r = wp.req("GET", "/wp/v2/posts", params={"status": "future", "per_page": 1, "orderby": "date",
                                               "order": "desc", "context": "edit"})
    if r.ok and r.json():
        terakhir = datetime.fromisoformat(r.json()[0]["date_gmt"]).replace(tzinfo=timezone.utc)
        mulai = max(mulai, terakhir + iv)
    return mulai, iv


def unggah_paket(wp, cfg, p, tayang=None):
    judul, paragraf = parse_md(ROOT / p["file_md"])
    slug = slugify(judul)
    r = wp.req("GET", "/wp/v2/posts", params={"slug": slug, "status": "any"})
    if r.ok and r.json():
        ada = r.json()[0]
        p.update(wp_post_id=ada["id"], wp_url=ada.get("link"), status_wp=ada.get("status"),
                 catatan_wp="sudah ada di WordPress; dilewati")
        return "sudah ada"
    ids, _ = id_meta(wp, cfg, p, wajib=True)
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
    data = {"title": judul, "content": ke_html(paragraf), "excerpt": ringkas(paragraf),
            "slug": slug, "status": cfg["status_wp"], "featured_media": media_id,
            "categories": ids["categories"], "tags": ids["tags"],
            "wilayah": ids["wilayah"], "rubrik": ids["rubrik"], "dapil": ids["dapil"]}
    if cfg.get("penulis_id"):
        data["author"] = cfg["penulis_id"]
    if cfg["status_wp"] == "future":
        if not tayang:
            raise RuntimeError("jadwal tayang kosong")
        data["date_gmt"] = tayang.strftime("%Y-%m-%dT%H:%M:%S")
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
    sesuai = all(set(ids[k]) <= set(vj.get(k, [])) for k in ("categories", "tags", "wilayah", "rubrik", "dapil"))
    if vj.get("featured_media") != media_id or not sesuai or not ex.strip():
        raise RuntimeError("verifikasi: foto/kategori/tag/wilayah/rubrik/dapil/excerpt tidak sesuai")
    p.update(wp_post_id=vj["id"], wp_url=vj.get("link"), status_wp=vj.get("status"),
             tgl_upload=datetime.now(WIB).isoformat(timespec="seconds"), catatan_wp="",
             sidik_meta=sidik_meta(cfg, p))
    if tayang:
        p["tgl_tayang"] = tayang.astimezone(WIB).isoformat(timespec="minutes")
    return "dibuat"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kering", action="store_true")
    ap.add_argument("--maks", type=int)
    ap.add_argument("--sinkron-semua", action="store_true",
                    help="cek ulang metadata semua post, bukan hanya yang baru/berubah")
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
            print(f"[KERING] {p['id']} | {p['wilayah']} -> {(cfg.get('slug_wilayah') or {}).get(p['wilayah'])} "
                  f"| kategori={p.get('kategori')} rubrik={p.get('rubrik')} dapil={p.get('dapil') or (cfg.get('dapil_per_kabkota') or {}).get(p.get('kabkota'))} tag={nama_tag(cfg, p)} | status={cfg['status_wp']} | slug={slugify(judul)} | foto={p['file_jpg']} ({p.get('ukuran_kb')} KB)")
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
    slot, iv = slot_pertama(wp, cfg) if cfg["status_wp"] == "future" else (None, None)
    for p in antrean:
        try:
            hasil = unggah_paket(wp, cfg, p, slot)
            print(f"{p['id']}: {hasil}" + (f" | tayang {slot.astimezone(WIB):%d/%m %H:%M} WIB" if slot and hasil == "dibuat" else ""))
            if slot and hasil == "dibuat":
                slot += iv
            ok += 1
        except Exception as e:  # noqa: BLE001
            p["catatan_wp"] = f"{type(e).__name__}: {e}"[:300]
            print(f"{p['id']}: GAGAL {p['catatan_wp']}")
        MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False))
        wp.jeda_ok()
    print(f"selesai: {ok}/{len(antrean)} berhasil")
    slot_ulang, iv_ulang = slot_pertama(wp, cfg) if any(x.get("jadwal_ulang") for x in m["paket"]) else (None, None)
    dilewati = 0
    for p in m["paket"]:
        if p.get("status") == "lengkap" and p.get("wp_post_id") and p.get("wp_media_id"):
            if not perlu_sinkron(cfg, p, a.sinkron_semua):
                dilewati += 1
                continue
            try:
                ada_ulang = bool(p.get("jadwal_ulang"))
                hasil = sinkron_meta(wp, cfg, p, slot_ulang)
                print(f"{p['id']}: {hasil}")
                p["sidik_meta"] = sidik_meta(cfg, p)
                if ada_ulang and not p.get("jadwal_ulang"):
                    print(f"  dijadwalkan ulang: tayang {slot_ulang.astimezone(WIB):%d/%m %H:%M} WIB")
                    slot_ulang += iv_ulang
            except Exception as e:  # noqa: BLE001
                p["catatan_wp"] = f"{type(e).__name__}: {e}"[:300]
                print(f"{p['id']}: GAGAL metadata {p['catatan_wp']}")
                hasil = "gagal"
            MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False))
            if hasil != "metadata sudah sesuai":
                wp.jeda_ok()  # jeda hanya setelah menulis ke WP; cek baca saja tidak perlu ditahan
    print(f"sinkron metadata dilewati (tidak berubah): {dilewati}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
