import re


SEGMENT_RE = re.compile(
    r"\[(\d+(?:\.\d+)?)\s*-\s*"
    r"(\d+(?:\.\d+)?)\]\s*(.*)"
)

SRT_TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$"
)

# Pola pembuka/hook yang memiliki potensi retensi tinggi
HOOK_PATTERNS = [
    # 1. Pertanyaan pancingan / provokatif
    (re.compile(
        r"\b(pernah\s+(?:gak|nggak|kah|tidak)|kenapa\s+(?:sih|banyak|orang)|"
        r"mengapa|tahu\s+(?:gak|nggak|kah|kan)|sadar\s+gak|apa\s+yang\s+terjadi\s+kalau|"
        r"gimana\s+caranya|bagaimana\s+cara)\b", re.I), 10, "Pertanyaan Hook"),

    # 2. Pernyataan kontrarian / rahasia / kesalahan fatal
    (re.compile(
        r"\b(rahasia|kunci(?:\s+utama(?:nya)?)?|fakta(?:nya)?|kesalahan\s+(?:terbesar|fatal)|"
        r"jangan\s+pernah|banyak\s+(?:orang\s+)?(?:nggak|tidak|salah)|semua\s+orang\s+salah|"
        r"kebanyakan\s+orang|trik\s+(?:rahasia|tersembunyi)|aturan\s+emas)\b", re.I), 11, "Kontrarian & Rahasia"),

    # 3. Angka / skala / hasil konkret
    (re.compile(
        r"\b(\d+\s*(?:juta|miliar|ribu|persen|%|hari|bulan|tahun|digit|kali\s+lipat)|"
        r"omzet|profit|gaji|modal|cuan|hasilnya)\b", re.I), 9, "Angka & Hasil Konkret"),

    # 4. Pengungkapan mengejutkan & emosi ekstrem
    (re.compile(
        r"\b(ternyata|beneran|sumpah|gila\s+sih|luar\s+biasa|parah\s+banget|"
        r"hampir\s+(?:bangkrut|drop|mati|gagal)|titik\s+balik|momen\s+terberat|"
        r"plot\s+twist|yang\s+bikin\s+kaget|akhirnya\s+sadar)\b", re.I), 9, "Emosi & Revelation"),
]

# Kata kunci yang menunjukkan nilai wawasan / solusi di tengah clip
BODY_INSIGHT_PATTERNS = re.compile(
    r"\b(kuncinya|solusinya|caranya|strateginya|langkahnya|polanya|"
    r"karena|sebab|akibatnya|berubah|belajar|pengalaman|paham|"
    r"masalah|tantangan|solusi|metode|efektif|berhasil)\b",
    re.I,
)

# Kata kunci penutup / kesimpulan / punchline
PUNCHLINE_PATTERNS = re.compile(
    r"\b(jadi\s+(?:kuncinya|kesimpulannya|intinya)|makanya|itulah\s+kenapa|"
    r"pelajarannya|pesan\s+moral|mulai\s+sekarang)\b",
    re.I,
)

# Penalti untuk pembukaan basi / basa-basi / sponsor / intro
BAD_HOOK = re.compile(
    r"\b(halo\s+guys|selamat\s+datang|welcome\s+back|nama\s+saya|kembali\s+lagi|"
    r"tes\s+satu\s+dua|gimana\s+kabarnya|jangan\s+lupa\s+like|subscribe|"
    r"sponsor\s+video\s+ini|link\s+di\s+deskripsi|terima\s+kasih\s+sudah\s+menonton|"
    r"podcast\s+ini\s+disponsori)\b",
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
    raw_segments = []
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
                raw_segments.append({
                    "start": start,
                    "end": end,
                    "text": text,
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
                raw_segments.append({
                    "start": start,
                    "end": end,
                    "text": text,
                })

        index += 1

    return raw_segments


def merge_into_sentences(raw_segments):
    """
    Menggabungkan penggalan subtitle pendek menjadi kalimat / pemikiran utuh
    berdasarkan tanda baca dan jeda waktu pembicara.
    """
    if not raw_segments:
        return []

    sentences = []
    current_start = raw_segments[0]["start"]
    current_end = raw_segments[0]["end"]
    current_texts = [raw_segments[0]["text"]]

    for i in range(1, len(raw_segments)):
        seg = raw_segments[i]
        prev_text = current_texts[-1]
        gap = seg["start"] - current_end

        # Kalimat dianggap selesai jika ada tanda baca selesai atau jeda hening > 0.8 detik
        ends_sentence = prev_text.endswith((".", "!", "?", ":", "..."))
        is_long_pause = gap > 0.8

        if ends_sentence or is_long_pause or (current_end - current_start >= 12.0):
            full_text = " ".join(current_texts).strip()
            if full_text:
                sentences.append({
                    "start": current_start,
                    "end": current_end,
                    "text": full_text,
                    "words": len(full_text.split()),
                })
            current_start = seg["start"]
            current_end = seg["end"]
            current_texts = [seg["text"]]
        else:
            current_texts.append(seg["text"])
            current_end = max(current_end, seg["end"])

    full_text = " ".join(current_texts).strip()
    if full_text:
        sentences.append({
            "start": current_start,
            "end": current_end,
            "text": full_text,
            "words": len(full_text.split()),
        })

    return sentences


def evaluate_hook(sentence):
    """Mengevaluasi kualitas hook di awal kalimat."""
    text = sentence["text"]
    score = 0
    tag = "Standard"

    if BAD_HOOK.search(text):
        return -15, "Intro/Filler Basi"

    for pattern, weight, label in HOOK_PATTERNS:
        if pattern.search(text):
            score += weight
            tag = label

    # Tambahan nilai jika berupa kalimat tanya langsung
    if "?" in text:
        score += 3

    return score, tag


def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def find_candidates(transcript, limit=10):
    raw_segments = parse(transcript)
    if not raw_segments:
        return []

    sentences = merge_into_sentences(raw_segments)
    if not sentences:
        return []

    potential_clips = []
    num_sentences = len(sentences)

    for i in range(num_sentences):
        hook_sentence = sentences[i]
        hook_score, hook_tag = evaluate_hook(hook_sentence)

        # Abaikan pembuka yang buruk atau tanpa sinyal ketertarikan sama sekali
        if hook_score <= 0:
            continue

        clip_start = hook_sentence["start"]
        best_clip = None

        # Perluas klip ke depan untuk menemukan durasi optimal 25s - 60s
        accumulated_text = [hook_sentence["text"]]
        accumulated_words = hook_sentence["words"]

        for j in range(i + 1, min(i + 25, num_sentences)):
            next_sent = sentences[j]
            clip_end = next_sent["end"]
            duration = clip_end - clip_start

            accumulated_text.append(next_sent["text"])
            accumulated_words += next_sent["words"]

            # Jika durasi melebihi batas maksimal short (65 detik), hentikan pencarian
            if duration > 65.0:
                break

            # Jika durasi sudah mencapai rentang ideal video pendek (22s - 60s)
            if duration >= 22.0:
                full_clip_text = " ".join(accumulated_text)

                # Hitung nilai isi wawasan
                insight_matches = len(BODY_INSIGHT_PATTERNS.findall(full_clip_text))
                insight_score = min(12, insight_matches * 3)

                # Evaluasi punchline / penutup
                punchline_score = 4 if PUNCHLINE_PATTERNS.search(next_sent["text"]) else 0

                # Evaluasi kecepatan bicara (densitas kata / detik)
                wps = accumulated_words / max(1.0, duration)
                pacing_score = 4 if (2.0 <= wps <= 4.0) else 1

                # Durasi sweet spot video pendek adalah 30-50 detik
                duration_bonus = 4 if (30.0 <= duration <= 52.0) else 2

                total_score = (
                    (hook_score * 2)
                    + insight_score
                    + punchline_score
                    + pacing_score
                    + duration_bonus
                )

                candidate_entry = {
                    "context_start": clip_start,
                    "context_end": clip_end,
                    "duration": duration,
                    "score": total_score,
                    "hook_tag": hook_tag,
                    "hook_snippet": hook_sentence["text"][:75] + ("..." if len(hook_sentence["text"]) > 75 else ""),
                }

                if best_clip is None or candidate_entry["score"] > best_clip["score"]:
                    best_clip = candidate_entry

        if best_clip and best_clip["score"] >= 15:
            potential_clips.append(best_clip)

    # Urutkan berdasarkan skor tertinggi (kandidat paling berpotensi viral)
    potential_clips.sort(key=lambda x: x["score"], reverse=True)

    # Non-Maximal Suppression: Hilangkan kandidat yang saling tumpang tindih (>30%)
    selected = []
    for cand in potential_clips:
        c_start = cand["context_start"]
        c_end = cand["context_end"]

        overlap = False
        for s in selected:
            s_start = s["context_start"]
            s_end = s["context_end"]
            overlap_duration = max(0.0, min(c_end, s_end) - max(c_start, s_start))
            if overlap_duration > 0.3 * min(cand["duration"], s["duration"]):
                overlap = True
                break

        if not overlap:
            selected.append(cand)

        if len(selected) >= limit:
            break

    # Urutkan kembali berdasarkan urutan kronologis waktu kemunculan di video
    selected.sort(key=lambda x: x["context_start"])

    for idx, item in enumerate(selected, 1):
        item["id"] = idx

    return selected


def build_gemini_prompt(candidates, source_url=""):
    lines = [
        "URL YouTube:",
        source_url.strip() if source_url else "(URL tidak disertakan)",
        "",
        "Daftar Timestamp Kandidat Klip Berpotensi Tinggi:",
    ]

    if not candidates:
        lines.append("(Tidak ada kandidat klip yang memenuhi kriteria viral/insight)")
    else:
        for item in candidates:
            c_start = item["context_start"]
            c_end = item["context_end"]
            dur = item.get("duration", c_end - c_start)
            time_formatted = f"{format_time(c_start)} - {format_time(c_end)}"
            sec_formatted = f"{c_start:.3f} - {c_end:.3f}"
            tag = item.get("hook_tag", "Insight")
            hook_text = item.get("hook_snippet", "")

            lines.append(
                f"- Kandidat #{item['id']}: {time_formatted} (Detik: {sec_formatted}, Durasi: {int(dur)}s) [{tag}]\n"
                f"  Hook: \"{hook_text}\""
            )

    lines.extend([
        "",
        "Tugas Validator Gemini AI:",
        "1. Dari daftar kandidat di atas, pilih 1 sampai 3 klip terbaik dengan hook terkuat dan retensi tertinggi.",
        "2. Tentukan timestamp presisi START dan END untuk dipotong menjadi Shorts/Reels/TikTok.",
        "3. Berikan alasan singkat mengapa klip tersebut paling berpotensi viral.",
    ])

    return "\n".join(lines)

