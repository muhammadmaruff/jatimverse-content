# Aturan riset harian Jatimverse.id (dibaca bersama PETUNJUK_BATCH.md)

Jika dua dokumen berbeda, PETUNJUK_BATCH.md dan config/sumber.json yang berlaku untuk langkah teknis; dokumen ini untuk kuota, pemilihan topik, dan penulisan.

## Mode tanpa pengawas
Jangan mengajukan pertanyaan. Ambil pembacaan paling masuk akal, catat asumsi di `catatan`, kerjakan sampai selesai. Yang gagal dicatat lalu lanjut. Jika akses repo gagal, berhenti dan laporkan (jangan mencari jalan memutar). Jangan meminta, menulis, atau mencetak kata sandi atau token apa pun.

## Kuota per batch (total 20 paket per hari)
- Batch 1 (7): Surabaya Raya 4 (Surabaya, Sidoarjo, Gresik, Kota/Kab Mojokerto; berita se-Jatim maks 1 topik) + Malang Raya 3 (Kota Malang, Kab Malang, Kota Batu).
- Batch 2 (7): Mataraman 4 (Madiun, Magetan, Ngawi, Ponorogo, Pacitan, Trenggalek, Tulungagung, Blitar, Kediri, Nganjuk, Jombang; kota dan kabupaten) + Pantura 3 (Tuban, Lamongan, Bojonegoro).
- Batch 3 (6): Tapal Kuda 4 (Pasuruan, Probolinggo, Lumajang, Jember, Bondowoso, Situbondo, Banyuwangi) + Madura 2 (Bangkalan, Sampang, Pamekasan, Sumenep).
- Kuota satu wilayah boleh diisi dari kab/kota mana pun di dalam kelompoknya.
- Kuota tak terpenuhi: perluas ke 48 jam (`tanda_48j: true`). Masih kurang: alihkan sisa ke wilayah lain dalam batch yang sama yang paling ramai, catat alasannya. Jangan memaksakan berita lama.

## Sumber sah
Hanya domain .go.id milik pemprov/dinas, pemkot/pemkab, DPRD, dan instansi vertikal di Jatim. Bukan media, blog, medsos, sch.id, atau situs desa. Satu topik boleh diperkuat beberapa situs resmi; catat semua URL di `url_sumber`.

## Pemilihan topik
- Tiap paket satu peristiwa berbeda, bukan sekadar berbeda URL. Cek `manifest.json` (judul dan url_sumber) dan jangan ulangi topik yang sudah ada.
- Peristiwa yang sama di banyak situs (misalnya penghargaan/awards yang sama) = satu paket saja.
- Usahakan beragam isu: pelayanan publik, infrastruktur, ekonomi/UMKM, kesehatan, pendidikan, pertanian, keamanan, lingkungan, sosial budaya. Maks 2 topik seremonial per batch (peresmian, kunjungan, penghargaan).
- Hanya rilis yang tanggal terbitnya pasti masuk rentang. Tanggal tak jelas atau tanggal kegiatan lama: lewati.
- Rilis dari kepolisian/BNN boleh bila domainnya .go.id; rilis UKM kampus bukan.

## Penulisan
- Straight news, piramida terbalik, paragraf 1–3 kalimat. Judul lugas maks ±70 karakter, tanpa clickbait.
- Dateline kota huruf besar ("SURABAYA –"). Lead memuat 5W1H inti; kutipan pejabat dengan atribusi jelas.
- Netralkan bahasa promosi humas: klaim keberhasilan ditulis sebagai pernyataan narasumber ("menurut Pemkab ..."). Tulis ulang dengan kalimat sendiri.
- DILARANG menambah fakta, angka, kutipan, atau nama yang tidak ada di sumber. Jumlah kata minimal `aturan.ambang_kata` (config/sumber.json); bahan kurang: pakai konteks dari situs resmi lain (catat URL), atau ganti topik.
- Tanpa baris "Sumber:" di akhir.
- Metadata manifest: `kategori` (politik, ekonomi, jelajah, viral, bola) dan `rubrik` (biar-paham, cuan-jatim, derbi-jatim, jelajah-jatim, suara-arek, wakil-kita) dipilih yang paling sesuai tema (ekonomi/UMKM → ekonomi + cuan-jatim; olahraga → bola + derbi-jatim; wisata/budaya → jelajah + jelajah-jatim; DPRD/politik → politik + wakil-kita; pelayanan publik/warga → politik + suara-arek; penjelasan kebijakan → biar-paham). `tag`: 3–5 tag spesifik (tema, tokoh, instansi, lokasi). `dapil` boleh dikosongkan bila `config/wordpress.json` sudah memetakannya dari kabkota.

## Pembagian tugas pipeline
Tugas riset berhenti setelah artikel dan manifest (status `butuh_gambar`, `url_foto_sumber` terisi) di-commit dan di-push. Foto, verifikasi, dan unggah WordPress dikerjakan otomatis oleh workflow GitHub `pipeline-harian` (11.00 WIB). Jangan menjalankan `proses-foto`, `verifikasi.py --tulis`, atau `upload_wp.py` dari tugas riset.

## Hal yang tidak boleh disentuh
Paket berstatus `lengkap` atau yang punya `wp_post_id`, config/wordpress.json, scripts/, dan workflow. Hanya tambahkan paket baru ke manifest dan berkas baru di artikel/. Saat push: `git pull --rebase origin main` dulu; jika manifest bentrok, baca versi terbaru dan terapkan ulang HANYA tambahan sendiri, jangan menimpa isi lain.
