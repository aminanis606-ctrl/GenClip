import sys

from whisper import transcript
from prefilter import find_candidates
from validator import validate
from downloader import download_clip


def main():
    if len(sys.argv) != 2:
        print('Pakai: python pipeline.py "YOUTUBE_URL"')
        return

    url = sys.argv[1].strip()

    print("[1] AUDIO + TRANSCRIPT")

    transcript_file = transcript(url)

    if not transcript_file:
        return

    text = transcript_file.read_text(
        encoding="utf-8"
    )

    print("[2] PREFILTER")

    candidates = find_candidates(text)

    print(
        f"[PREFILTER] {len(candidates)} kandidat"
    )

    if not candidates:
        print("[STOP] Kandidat kosong.")
        return

    print("[3] VALIDATOR")

    from prefilter import group_candidates

    groups = group_candidates(candidates)
    clips = []

    group_sizes = [len(group) for group in groups]

    print(
        f"[GROUPING] {len(groups)} group"
    )

    print(
        f"[GROUPING] sizes={','.join(map(str, group_sizes))}"
    )

    if group_sizes:
        print(
            f"[GROUPING] max_group={max(group_sizes)}"
        )
    else:
        print("[GROUPING] max_group=0")

    for index, group in enumerate(groups, 1):
        print(
            f"[VALIDATOR] batch {index}/{len(groups)}: "
            f"{len(group)} kandidat"
        )

        clips.extend(validate(group))

    print(
        f"[VALIDATOR] {len(clips)} clip final"
    )

    if not clips:
        print("[STOP] Tidak ada clip valid.")
        return

    print("[4] FINAL TIMESTAMPS")

    for i, clip in enumerate(clips, 1):
        print(
            f"[{i}] "
            f"{clip['start']:.1f}-"
            f"{clip['end']:.1f}s "
            f"{clip['title']}"
        )

    print("[5] DOWNLOAD VIDEO")

    for i, clip in enumerate(clips, 1):
        download_clip(url, clip, i)


if __name__ == "__main__":
    main()
