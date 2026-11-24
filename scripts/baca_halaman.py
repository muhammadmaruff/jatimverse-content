#!/usr/bin/env python3
"""Pembaca halaman untuk sesi riset (sesi cloud tidak punya WebFetch dan tidak bisa mengakses .go.id).
Dijalankan oleh workflow baca-halaman di GitHub. Hasil: bacaan/hasil.md

  python scripts/baca_halaman.py daftar            # semua halaman daftar di config/sumber.json
  python scripts/baca_halaman.py artikel URL [URL...]
  python scripts/baca_halaman.py daftar-url URL [URL...]   # halaman daftar tertentu
"""
import json, re, sys, pathlib, urllib3
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings()
UA = {"User-Agent": "Mozilla/5.0 (compatible; JatimverseBot/1.0)", "Accept-Language": "id,en;q=0.8"}
OUT = pathlib.Path("bacaan"); OUT.mkdir(exist_ok=True)
MAX_ART = 7000

def ambil(url):
    try:
        r = requests.get(url, headers=UA, timeout=(10, 20), verify=False, allow_redirects=True)
        r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
        return r.status_code, r.text
    except Exception as e:
        return 0, f"GAGAL: {type(e).__name__}: {e}"

def bersih(soup):
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "aside", "svg"]):
        t.decompose()

def meta(soup, *names):
    for n in names:
        t = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if t and t.get("content"):
            return t["content"].strip()
    return ""

def artikel(url):
    kode, html = ambil(url)
    if not kode or kode >= 400:
        return f"## {url}\nSTATUS {kode} {html[:200] if not kode else ''}\n"
    soup = BeautifulSoup(html, "html.parser")
    judul = meta(soup, "og:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    tgl = meta(soup, "article:published_time", "datePublished", "date")
    foto = meta(soup, "og:image", "twitter:image")
    imgs = []
    for im in soup.find_all("img"):
        s = im.get("src") or im.get("data-src")
        if s and not s.startswith("data:"):
            imgs.append(urljoin(url, s))
    bersih(soup)
    teks = re.sub(r"[ \t]+", " ", soup.get_text("\n"))
    teks = re.sub(r"\n\s*\n+", "\n", teks).strip()
    return (f"## {url}\nSTATUS {kode}\nJUDUL: {judul}\nTGL_META: {tgl}\nOG_IMAGE: {foto}\n"
            f"GAMBAR: {' | '.join(imgs[:8])}\nISI:\n{teks[:MAX_ART]}\n")

def daftar(url):
    kode, html = ambil(url)
    if not kode or kode >= 400:
        return f"## DAFTAR {url}\nSTATUS {kode} {html[:200] if not kode else ''}\n"
    soup = BeautifulSoup(html, "html.parser")
    bersih(soup)
    seen, baris = set(), []
    for a in soup.find_all("a", href=True):
        h = urljoin(url, a["href"]); t = " ".join(a.get_text(" ").split())
        if len(t) < 25 or h in seen or h.rstrip("/") == url.rstrip("/"):
            continue
        seen.add(h)
        # ikutkan teks induk (sering memuat tanggal)
        p = a.find_parent(["li", "article", "div"])
        konteks = " ".join(p.get_text(" ").split())[:220] if p else ""
        baris.append(f"- {t[:140]} | {h} | {konteks if konteks != t else ''}")
    return f"## DAFTAR {url}\nSTATUS {kode}\n" + "\n".join(baris[:45]) + "\n"

def jalan(fn, urls, batas=150):
    """Jalankan paralel dengan batas total waktu; yang belum selesai dicatat TIMEOUT."""
    from concurrent.futures import wait
    ex = ThreadPoolExecutor(8)
    fs = [ex.submit(fn, u) for u in urls]
    wait(fs, timeout=batas)
    hasil = [f.result() if f.done() else f"## {u}\nTIMEOUT (> {batas} dtk)\n" for f, u in zip(fs, urls)]
    ex.shutdown(wait=False, cancel_futures=True)
    return hasil

def main():
    mode, args = sys.argv[1], sys.argv[2:]
    if mode == "daftar":
        cfg = json.load(open("config/sumber.json"))["situs"]
        urls = [v["daftar"] for v in cfg.values()
                if isinstance(v, dict) and v.get("daftar") and v.get("status") in ("ok", "sebagian")]
        urls += ["https://www.surabaya.go.id/", "https://sidoarjokab.go.id/", "https://www.malangkota.go.id/",
                 "https://www.gresikkab.go.id/", "https://www.lamongankab.go.id/", "https://www.bojonegorokab.go.id/",
                 "https://www.banyuwangikab.go.id/", "https://www.ponorogo.go.id/"]
        parts = jalan(daftar, list(dict.fromkeys(urls)))
    elif mode == "daftar-url":
        parts = jalan(daftar, args)
    else:
        parts = jalan(artikel, args)
    (OUT / "hasil.md").write_text("\n".join(parts), encoding="utf-8")
    print("selesai", len(parts), flush=True)
    import os; os._exit(0)

main()
