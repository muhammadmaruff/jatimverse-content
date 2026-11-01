# Petunjuk menjalankan batch (untuk Claude)

Baca `manifest.json` dan `config/sumber.json` lebih dulu. Jangan mencari ulang topik yang sudah di manifest.

## Urutan kerja
1. Waktu: ambil WIB dari `TZ=Asia/Jakarta date`. Alat waktu bisa mengembalikan "unavailable".
   Rentang: 24 jam (Selasa–Sabtu), 48 jam (Minggu dan Senin, semua paket `tanda_48j: true`).
2. Riset: untuk tiap wilayah batch, baca situs berstatus `ok` di `config/sumber.json` dulu
   (satu WebFetch per halaman daftar). Situs `websearch`/`blokir`: WebSearch dengan `allowed_domains`.
   Saring tanggal dulu dari URL/ID (unix timestamp di Sidoarjo dan Mojokerto Kab, tanggal di URL Madiun Kota).
3. Kumpulkan kandidat 1,5x kuota. Baca penuh hanya kandidat terpilih, dengan pertanyaan spesifik
   (5W1H, kutipan + nama + jabatan, angka, tanggal terbit, URL foto utama).
4. Tulis artikel ke `artikel/{id}.md`: baris 1 judul (`# ...`), lalu dateline `KOTA –`, paragraf pendek,
   baris terakhir `Sumber: [instansi]`. Hanya fakta dari sumber. Kutipan langsung secukupnya, selebihnya tidak langsung.
   Jumlah kata minimal `aturan.ambang_kata`. Jika bahan kurang, ganti topik, jangan menambah fakta.
5. Tambahkan ke `manifest.json`: status `butuh_gambar`, isi `url_foto_sumber`, `jumlah_kata`, `file_md`, `kredit_foto`.
   (Hitung jumlah kata: isi di luar judul dan baris Sumber, dateline ikut dihitung.)
6. Commit dan push ke `main`.
7. Foto: jalankan workflow `proses-foto` (tanpa input):
   `gh api -X POST repos/muhammadmaruff/jatimverse-content/actions/workflows/proses-foto.yml/dispatches -f ref=main`
   Tunggu selesai, `git pull --rebase origin main`.
   Jika foto gagal, catatannya tertulis di manifest; JANGAN membuat gambar pengganti.
8. Verifikasi: `python3 scripts/verifikasi.py --tulis` (hanya paket lolos jadi `lengkap`).
   Commit dan push hasilnya.
9. Laporan: tabel ID | wilayah | judul | jumlah kata | ukuran foto | status, lalu satu baris lolos/target dan kekurangan.

## Batasan lingkungan cloud
- Shell tidak bisa mengakses .go.id. Semua unduhan foto lewat workflow GitHub.
- WebFetch gagal pada sebagian situs; itu bukan berarti situsnya mati. Pakai WebSearch dengan `allowed_domains`.
- Tidak memakai subagent. Artikel tidak ditampilkan di chat.
- Foto sumber kecil bisa tampak lembut setelah dibesarkan ke 1280x720. Tidak perlu dikoreksi.
- Jangan menjadwalkan otomatis sebelum pengguna meminta.

## Metadata editorial (wajib untuk unggah WordPress)
Setiap paket di manifest harus punya: `kategori` (politik, ekonomi, jelajah, viral, atau bola), `rubrik` (biar-paham, cuan-jatim, derbi-jatim, jelajah-jatim, suara-arek, atau wakil-kita), dan `tag` (minimal 3 tag topik spesifik dari isi berita). Wilayah dan kabupaten/kota ikut menjadi tag otomatis. Dapil dipetakan dari `kabkota` lewat `dapil_per_kabkota` di `config/wordpress.json` (atau field `dapil` per paket). Baris `Sumber:` tetap ada di berkas md untuk verifikasi, tetapi tidak ditayangkan.
