import subprocess
import requests

from youtube_transcript_api import YouTubeTranscriptApi

from config import API_KEY, TEMP


def run(cmd):
    return subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def video_id(url):
    result = subprocess.run(
        ["yt-dlp", "--get-id", url],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def transcript_from_youtube(vid):
    output = TEMP / f"{vid}_transcript.txt"

    try:
        api = YouTubeTranscriptApi()

        for languages in (["id", "en"], ["en", "id"]):
            try:
                fetched = api.fetch(
                    vid,
                    languages=languages
                )

                lines = []

                for item in fetched:
                    start = float(item.start)
                    end = start + float(item.duration)
                    text = item.text.strip()

                    if text and end > start:
                        lines.append(
                            f"[{start:.1f} - {end:.1f}] {text}"
                        )

                if lines:
                    output.write_text(
                        "\n".join(lines),
                        encoding="utf-8"
                    )
                    print(
                        f"[TRANSCRIPT] YouTube transcript "
                        f"ditemukan ({languages[0]})"
                    )
                    return output

            except Exception:
                continue

    except Exception:
        pass

    print("[TRANSCRIPT] Tidak tersedia. Fallback ke Whisper.")
    return None


def transcript(url):
    vid = video_id(url)

    if not vid:
        print("[ERROR] Video ID gagal.")
        return None

    audio = TEMP / f"{vid}.opus"
    optimized = TEMP / f"{vid}_whisper.m4a"
    output = TEMP / f"{vid}_transcript.txt"

    if output.exists() and output.stat().st_size > 100:
        print("[CACHE] Transcript ditemukan.")
        return output

    transcript_file = transcript_from_youtube(vid)

    if transcript_file:
        return transcript_file

    print("[AUDIO] Download audio penuh...")

    result = run([
        "yt-dlp", "-f", "bestaudio",
        "-o", str(audio), url
    ])

    if result.returncode != 0 or not audio.exists():
        print("[ERROR] Audio gagal.")
        return None

    result = run([
        "ffmpeg", "-y", "-i", str(audio),
        "-ac", "1", "-ar", "16000",
        "-c:a", "aac", "-b:a", "32k",
        str(optimized)
    ])

    if result.returncode != 0 or not optimized.exists():
        print("[ERROR] Optimasi audio gagal.")
        return None

    print("[WHISPER] Transkripsi...")

    try:
        with optimized.open("rb") as f:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                files={"file": ("audio.m4a", f, "audio/m4a")},
                data=[
                    ("model", "whisper-large-v3"),
                    ("response_format", "verbose_json"),
                    ("timestamp_granularities[]", "segment"),
                ],
                timeout=180,
            )

        if response.status_code != 200:
            print("[WHISPER ERROR]", response.text[:500])
            return None

        lines = []

        for s in response.json().get("segments", []):
            start = float(s.get("start", 0))
            end = float(s.get("end", 0))
            text = s.get("text", "").strip()

            if text and end > start:
                lines.append(
                    f"[{start:.1f} - {end:.1f}] {text}"
                )

        if not lines:
            print("[ERROR] Transcript kosong.")
            return None

        output.write_text(
            "\n".join(lines),
            encoding="utf-8"
        )

        print(f"[OK] {len(lines)} segment transcript.")
        return output

    except Exception as exc:
        print("[ERROR]", exc)
        return None
