import subprocess

from config import OUTPUT


def download_clip(url, clip, number):
    start = float(clip["start"])
    end = float(clip["end"])

    output = OUTPUT / f"clip_{number:02d}.mp4"

    print(
        f"[VIDEO] {number}: "
        f"{start:.1f}-{end:.1f}s"
    )

    result = subprocess.run(
        [
            "yt-dlp",
            "-f", "134",
            "--download-sections",
            f"*{start}-{end}",
            "-o", str(output),
            url
        ],
        check=False
    )

    if result.returncode != 0 or not output.exists():
        print(f"[FAILED] Clip {number}")
        return None

    print(f"[READY] {output}")
    return output
