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


def build_gemini_prompt(candidates, source_url=""):
    lines = [
        "Anda adalah validator clip dari transcript podcast.",
        "",
        "Tugas:",
        "1. Pilih kandidat yang paling layak menjadi short clip.",
        "2. Validasi konteks berdasarkan timestamp yang diberikan.",
        "3. Jangan mengarang timestamp.",
        "4. Gunakan hanya rentang waktu yang tersedia.",
        "5. Jika URL YouTube tersedia, gunakan URL tersebut.",
        "6. Hasil akhir harus siap dipaste ke YTDLnis.",
        "",
        "FORMAT OUTPUT:",
        "- Satu blok untuk setiap clip yang dipilih.",
        "- Sertakan timestamp START dan END.",
        "- Sertakan alasan singkat pemilihan.",
        "- Jika URL tersedia, sertakan perintah yt-dlp/YTDLnis yang sesuai.",
        "- Jangan memberikan penjelasan panjang di luar hasil.",
        "",
        "URL YOUTUBE:",
        source_url.strip() if source_url else "(tidak tersedia)",
        "",
        "KANDIDAT PREFILTER:",
    ]

    if not candidates:
        lines.append("(tidak ada kandidat)")
    else:
        for item in candidates:
            lines.extend([
                "",
                f"Kandidat #{item['id']}",
                f"Score: {item['score']}",
                f"Anchor: {item['anchor_start']:.3f} - {item['anchor_end']:.3f}",
                f"Context: {item['context_start']:.3f} - {item['context_end']:.3f}",
                "Transcript:",
                item["text"],
            ])

    return "\n".join(lines)


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

    selected = []

    for candidate in candidates:
        overlaps = any(
            candidate["anchor_start"] < item["anchor_end"]
            and candidate["anchor_end"] > item["anchor_start"]
            for item in selected
        )

        if not overlaps:
            selected.append(candidate)

        if len(selected) >= limit:
            break

    selected.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    for index, candidate in enumerate(selected, 1):
        candidate["id"] = index

    return selected
