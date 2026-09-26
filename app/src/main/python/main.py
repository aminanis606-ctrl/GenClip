from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi


def video_id(url):
    parsed = urlparse(url)

    if parsed.hostname in ("youtu.be", "www.youtu.be"):
        return parsed.path.strip("/")

    if parsed.hostname and parsed.hostname.endswith("youtube.com"):
        query_id = parse_qs(parsed.query).get("v")
        if query_id:
            return query_id[0]

        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live"):
            return parts[1]

    return None


def transcript_srt(url):
    vid = video_id(url)

    if not vid:
        raise ValueError("URL YouTube tidak valid.")

    api = YouTubeTranscriptApi()

    fetched = None
    for languages in (["id", "en"], ["en", "id"]):
        try:
            fetched = api.fetch(vid, languages=languages)
            break
        except Exception:
            continue

    if fetched is None:
        raise RuntimeError("Transcript YouTube tidak tersedia.")

    lines = []

    for index, item in enumerate(fetched, 1):
        start = float(item.start)
        end = start + float(item.duration)
        text = item.text.strip()

        if not text or end <= start:
            continue

        def timestamp(seconds):
            total_ms = round(seconds * 1000)
            hours, remainder = divmod(total_ms, 3600000)
            minutes, remainder = divmod(remainder, 60000)
            seconds, milliseconds = divmod(remainder, 1000)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

        lines.extend([
            str(index),
            f"{timestamp(start)} --> {timestamp(end)}",
            text,
            ""
        ])

    if not lines:
        raise RuntimeError("Transcript kosong.")

    return "\n".join(lines)


def status():
    return "Clipper Python core ready"
