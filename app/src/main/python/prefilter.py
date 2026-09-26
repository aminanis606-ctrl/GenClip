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


def build_gemini_prompt(candidates, source_url=""):
    lines = [
        "URL YouTube:",
        source_url.strip() if source_url else "(URL tidak disertakan)",
        "",
        "Daftar Timestamp Kandidat Klip:",
    ]

    if not candidates:
        lines.append("(Tidak ada kandidat klip ditemukan)")
    else:
        for item in candidates:
            c_start = item.get("context_start", item.get("anchor_start", 0.0))
            c_end = item.get("context_end", item.get("anchor_end", 0.0))
            time_formatted = f"{format_time(c_start)} - {format_time(c_end)}"
            sec_formatted = f"{c_start:.3f} - {c_end:.3f}"
            lines.append(
                f"- Kandidat #{item['id']}: {time_formatted} (Detik: {sec_formatted})"
            )

    lines.extend([
        "",
        "Tugas Validator Gemini AI:",
        "Validasi daftar timestamp kandidat di atas berdasarkan video pada URL tersebut.",
        "Tentukan kandidat klip terbaik dengan hook terkuat untuk dipotong menjadi video pendek.",
        "Berikan output timestamp awal dan akhir (START - END) yang presisi serta alasan singkatnya.",
    ])

    return "\n".join(lines)
