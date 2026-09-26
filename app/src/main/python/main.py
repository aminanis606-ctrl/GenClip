import re
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    VideoUnavailable,
    TranscriptsDisabled,
    NoTranscriptFound,
    RequestBlocked,
    IpBlocked
)


def video_id(url):
    if not url:
        return None

    cleaned = re.sub(r"\s+", "", str(url).strip())

    match = re.search(
        r"(?:v=|\/|youtu\.be\/|embed\/|shorts\/|^)([a-zA-Z0-9_-]{11})(?:[?&/#]|$)",
        cleaned
    )
    if match:
        return match.group(1)

    parsed = urlparse(cleaned)

    if parsed.hostname in ("youtu.be", "www.youtu.be"):
        return parsed.path.strip("/")

    if parsed.hostname and "youtube.com" in parsed.hostname:
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
        raise ValueError("URL YouTube tidak valid atau ID video tidak ditemukan.")

    api = YouTubeTranscriptApi()

    fetched = None
    fetch_error = None

    try:
        ts = api.list(vid)
        try:
            t = ts.find_transcript(["id", "en"])
        except Exception:
            try:
                t = next(iter(ts))
            except Exception:
                t = None

        if t is not None:
            fetched = t.fetch()
    except (RequestBlocked, IpBlocked):
        raise RuntimeError(
            "YouTube membatasi/memblokir permintaan dari IP server cloud emulator. "
            "Gunakan opsi tempel transcript SRT di bawah, atau uji APK di HP fisik Anda."
        )
    except VideoUnavailable:
        raise RuntimeError("Video YouTube ini tidak tersedia (telah dihapus atau ID video salah).")
    except TranscriptsDisabled:
        raise RuntimeError("Pembuat video menonaktifkan transcript/subtitle untuk video ini.")
    except Exception as e:
        fetch_error = e

    if fetched is None:
        for languages in (["id", "en"], ["en", "id"], ["en"], ["id"]):
            try:
                fetched = api.fetch(vid, languages=languages)
                if fetched:
                    break
            except (RequestBlocked, IpBlocked):
                raise RuntimeError(
                    "YouTube memblokir permintaan dari IP cloud ini. "
                    "Silakan tempel langsung transcript SRT di kotak bawah."
                )
            except VideoUnavailable:
                raise RuntimeError("Video YouTube ini tidak tersedia atau telah dihapus.")
            except Exception as e:
                fetch_error = e
                continue

    if fetched is None:
        err_msg = str(fetch_error) if fetch_error else "Tidak ada subtitle yang tersedia"
        raise RuntimeError(f"Transcript YouTube tidak tersedia: {err_msg}")

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
