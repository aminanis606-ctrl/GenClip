import re


SEGMENT_RE = re.compile(
    r"\[(\d+(?:\.\d+)?)\s*-\s*"
    r"(\d+(?:\.\d+)?)\]\s*(.*)"
)

SRT_TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$"
)

SIGNALS = re.compile(
    r"\b("
    r"karena|ternyata|tetapi|tapi|namun|akhirnya|"
    r"berhasil|gagal|masalah|solusi|pengalaman|"
    r"kesalahan|pelajaran|rahasia|pertama|terbesar|"
    r"mengapa|kenapa|bagaimana|uang|gaji|bisnis|"
    r"usaha|hasil|berubah|keputusan|"
    r"menurut saya|pernah|dulu|waktu itu"
    r")\b",
    re.I,
)

BAD = re.compile(
    r"\b("
    r"subscribe|like|comment|follow|jangan lupa|"
    r"terima kasih sudah menonton|website|qr code"
    r")\b",
    re.I,
)


def parse_timestamp(value):
    hours, minutes, seconds, millis = map(int, value)
    return (
        hours * 3600
        + minutes * 60
        + seconds
        + millis / 1000.0
    )


def parse(transcript):
    segments = []
    lines = transcript.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index].strip()

        legacy = SEGMENT_RE.match(line)
        if legacy:
            start = float(legacy.group(1))
            end = float(legacy.group(2))
            text = legacy.group(3).strip()

            if end > start and text:
                segments.append({
                    "start": start,
                    "end": end,
                    "text": text,
                    "raw": line,
                })

            index += 1
            continue

        srt = SRT_TIME_RE.match(line)
        if srt:
            groups = srt.groups()
            start = parse_timestamp(groups[:4])
            end = parse_timestamp(groups[4:])

            index += 1
            text_lines = []

            while index < len(lines) and lines[index].strip():
                text_lines.append(lines[index].strip())
                index += 1

            text = " ".join(text_lines).strip()

            if end > start and text:
                segments.append({
                    "start": start,
                    "end": end,
                    "text": text,
                    "raw": f"[{start:.3f} - {end:.3f}] {text}",
                })

        index += 1

    return segments


def score(segment):
    text = segment["text"]
    words = len(text.split())
    value = 0

    if 8 <= words <= 60:
        value += 2

    if SIGNALS.search(text):
        value += 4

    if "?" in text:
        value += 2

    if BAD.search(text):
        value -= 8

    return value


def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def find_candidates(transcript, limit=20):
    segments = parse(transcript)
    candidates = []

    for index, segment in enumerate(segments):
        value = score(segment)

        if value <= 0:
            continue

        anchor_start = segment["start"]
        anchor_end = segment["end"]
        anchor_duration = anchor_end - anchor_start

        context_budget = max(
            0.0,
            70.0 - anchor_duration
        )
        before = context_budget / 2.0
        after = context_budget - before

        start = max(0.0, anchor_start - before)
        end = anchor_end + after

        context = [
            s for s in segments
            if s["end"] >= start and s["start"] <= end
        ]

        candidates.append({
            "anchor_start": anchor_start,
            "anchor_end": anchor_end,
            "context_start": start,
            "context_end": end,
            "score": value,
            "text": "\n".join(
                s["raw"] for s in context
            ),
        })

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    # Ambil top kandidat hingga limit=20 tanpa membuang karena overlap
    selected = candidates[:limit]

    # Urutkan secara kronologis
    selected.sort(
        key=lambda item: item["anchor_start"]
    )

    for index, candidate in enumerate(selected, 1):
        candidate["id"] = index

    return selected


def group_candidates(candidates):
    """Group candidates into transitive overlapping context components."""
    groups = []

    for candidate in candidates:
        overlapping = []

        for index, group in enumerate(groups):
            if any(
                candidate["context_start"] < item["context_end"]
                and candidate["context_end"] > item["context_start"]
                for item in group
            ):
                overlapping.append(index)

        if not overlapping:
            groups.append([candidate])
            continue

        merged = [candidate]

        for index in reversed(overlapping):
            merged.extend(groups.pop(index))

        groups.append(merged)

    # Urutkan kandidat dalam tiap group berdasarkan context_start
    for group in groups:
        group.sort(key=lambda item: item["context_start"])

    # Urutkan groups berdasarkan context_start paling awal
    groups.sort(key=lambda group: min(item["context_start"] for item in group))

    return groups


def build_gemini_prompt(groups, source_url=""):
    # Mendukung input baik berupa hasil group_candidates (list of groups)
    # maupun flat list candidates jika dipanggil secara legacy
    if groups and isinstance(groups, (list, tuple)):
        first = groups[0]
        if isinstance(first, dict):
            groups = group_candidates(groups)
    elif not groups:
        groups = []

    target_url = source_url.strip() if source_url else "<URL_YOUTUBE>"

    lines = [
        "URL YouTube:",
        target_url,
        "",
        "=== KELOMPOK KANDIDAT PREFILTER (GROUPS) ===",
        "Kandidat di bawah telah dikelompokkan berdasarkan tumpang tindih waktu/konteks (transitive overlap).",
        "Kandidat dalam satu group harus dinilai bersamaan.",
        "",
    ]

    if not groups:
        lines.append("(Tidak ada kelompok kandidat ditemukan)")
    else:
        for g_idx, group in enumerate(groups, 1):
            g_start = min(c["context_start"] for c in group)
            g_end = max(c["context_end"] for c in group)
            lines.append(
                f"--- GROUP {g_idx} ({len(group)} kandidat, Rentang Konteks: {format_time(g_start)} - {format_time(g_end)} / {g_start:.1f}s - {g_end:.1f}s) ---"
            )
            for c in group:
                lines.extend([
                    f"CANDIDATE {c['id']}",
                    f"ANCHOR: {c['anchor_start']:.3f} - {c['anchor_end']:.3f} ({format_time(c['anchor_start'])} - {format_time(c['anchor_end'])})",
                    f"AVAILABLE_CONTEXT: {c['context_start']:.3f} - {c['context_end']:.3f} ({format_time(c['context_start'])} - {format_time(c['context_end'])})",
                    "TRANSCRIPT:",
                    c.get("text", "").strip(),
                    "",
                ])

    lines.extend([
        "=== ATURAN EVALUASI & VALIDASI ===",
        "1. Evaluasi SETIAP GROUP secara independen dan BERURUTAN mulai dari GROUP 1 sampai GROUP terakhir. Tidak boleh melewati group mana pun.",
        "2. Sebelum membuat daftar clip final, Anda WAJIB menulis satu baris evaluasi untuk SETIAP GROUP dengan format persis:",
        "   GROUP N: STRONG / WEAK / REJECT — alasan singkat",
        "   Arti keputusan:",
        "   - STRONG: Terdapat setidaknya satu kandidat yang berpotensi menjadi clip mandiri yang kuat.",
        "   - WEAK: Ada materi tetapi tidak cukup kuat/mandiri untuk dijadikan clip.",
        "   - REJECT: Tidak layak dijadikan clip.",
        "",
        "3. Setelah seluruh GROUP dievaluasi, susun 'DAFTAR CLIP TERPILIH' hanya dari kandidat yang benar-benar layak.",
        "   Jangan memaksakan jumlah clip tertentu.",
        "4. Jika tidak ada clip yang layak dari SEMUA GROUP:",
        "   - Tulis tepat: TIDAK ADA KLIP LAYAK",
        "   - JANGAN menghasilkan command yt-dlp apa pun.",
        "",
        "=== ATURAN PEMILIHAN CLIP ===",
        "5. Untuk setiap clip terpilih, tentukan:",
        "   - GROUP",
        "   - CANDIDATE",
        "   - START (format HH:MM:SS atau MM:SS)",
        "   - END (format HH:MM:SS atau MM:SS)",
        "   - DURASI",
        "   - JUDUL/TOPIK",
        "   - ALASAN",
        "   - KUTIPAN AWAL",
        "   - KUTIPAN AKHIR",
        "6. KUTIPAN AWAL dan KUTIPAN AKHIR HARUS dikutip persis dari teks 'TRANSCRIPT' yang diberikan dalam prompt. JANGAN mengarang kutipan.",
        "   Kutipan awal membuktikan titik START alami, dan kutipan akhir membuktikan titik END alami.",
        "7. START dan END harus:",
        "   - Berada di dalam AVAILABLE_CONTEXT kandidat terkait.",
        "   - Tidak memotong kalimat dan tidak memotong pemikiran pembicara.",
        "   - Mencakup setup yang diperlukan dan mencakup explanation/reveal/result/payoff yang diperlukan.",
        "8. Durasi clip valid berada pada rentang 25–70 detik (diutamakan 30–60 detik).",
        "9. Kelengkapan cerita, alur, setup, dan payoff SELALU lebih penting daripada mengejar durasi tertentu. Jangan memotong clip 65–70 detik hanya untuk membuatnya lebih pendek.",
        "10. Jangan memilih kandidat hanya karena ANCHOR-nya memiliki score PREFILTER tinggi. Transcript dan konteks tetap menjadi dasar keputusan.",
        "",
        "=== ATURAN COMMAND YT-DLP ===",
        "11. Jika ada satu atau lebih clip terpilih, Anda HARUS menghasilkan TEPAT SATU command shell yt-dlp untuk SEMUA clip tersebut.",
        "    Satu response = satu command yt-dlp.",
        "12. Gunakan SATU URL YouTube dan SATU invocation yt-dlp.",
        "13. Untuk SETIAP clip terpilih, gunakan satu:",
        '    --download-sections "*START-END"',
        '    Contoh dua clip: --download-sections "*00:02:46-00:03:16" --download-sections "*00:07:44-00:08:14"',
        "    Jangan membuat command yt-dlp terpisah untuk masing-masing clip.",
        "14. Command WAJIB menggunakan format kompatibel ClipClip:",
        '    -f "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]"',
        '    JANGAN menggunakan "bv*+ba/b" atau "-f 134".',
        "15. Command WAJIB menggunakan:",
        "    --merge-output-format mp4",
        "16. Output diarahkan ke:",
        "    /storage/emulated/0/Movies/GenClip/",
        "17. Gunakan output template yang memastikan beberapa --download-sections tidak menimpa file satu sama lain, memuat judul yang disanitasi (tanpa karakter terlarang / \\ : * ? \" < > |) serta timestamp START dan END:",
        '    -o "/storage/emulated/0/Movies/GenClip/%(title).40s_%(section_start)s-%(section_end)s.%(ext)s"',
        "18. Anda HANYA menghasilkan command, BUKAN menjalankannya. Jangan buat command untuk clip yang ditolak.",
        "",
        "=== FORMAT RESPONSE GEMINI ===",
        "Respons Anda HARUS mengikuti urutan berikut:",
        "",
        "EVALUASI GROUP",
        "GROUP 1: STRONG / WEAK / REJECT — [alasan singkat]",
        "GROUP 2: STRONG / WEAK / REJECT — [alasan singkat]",
        "(tuliskan evaluasi satu baris untuk SETIAP GROUP secara berurutan)",
        "",
        "DAFTAR CLIP TERPILIH",
        "(Jika tidak ada klip yang layak dari semua group, tulis TEPAT:)",
        "TIDAK ADA KLIP LAYAK",
        "(Jika ada klip layak, tulis untuk setiap clip terpilih:)",
        "- GROUP: [nomor group]",
        "- CANDIDATE: [id kandidat]",
        "- START: [HH:MM:SS atau MM:SS]",
        "- END: [HH:MM:SS atau MM:SS]",
        "- DURASI: [durasi dalam detik]",
        "- JUDUL/TOPIK: [judul singkat bersih dari karakter ilegal filesystem]",
        "- ALASAN: [alasan singkat]",
        "- KUTIPAN AWAL: \"[kutipan persis dari transcript di titik START]\"",
        "- KUTIPAN AKHIR: \"[kutipan persis dari transcript di titik END]\"",
        "",
        "SATU COMMAND YT-DLP",
        "(Hanya jika ada clip terpilih. JANGAN tampilkan bagian ini jika TIDAK ADA KLIP LAYAK)",
        f'yt-dlp -f "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]" --merge-output-format mp4 --download-sections "*START_CLIP1-END_CLIP1" --download-sections "*START_CLIP2-END_CLIP2" -o "/storage/emulated/0/Movies/GenClip/%(title).40s_%(section_start)s-%(section_end)s.%(ext)s" "{target_url}"',
    ])

    return "\n".join(lines)
