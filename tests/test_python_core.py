import unittest
import sys
from pathlib import Path

# Add app/src/main/python to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app" / "src" / "main" / "python"))

from main import video_id
from prefilter import parse, score, find_candidates, group_candidates, build_gemini_prompt


class TestPythonCore(unittest.TestCase):

    def test_video_id_extraction(self):
        self.assertEqual(video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(video_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(video_id("dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_prefilter_parse_srt(self):
        srt_text = (
            "1\n00:00:01,000 --> 00:00:04,500\nSelamat datang di podcast ini.\n\n"
            "2\n00:00:05,000 --> 00:00:09,200\nHari ini kita membahas rahasia sukses omzet 1 miliar."
        )
        segments = parse(srt_text)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["start"], 1.0)
        self.assertEqual(segments[0]["end"], 4.5)
        self.assertIn("podcast", segments[0]["text"])

    def test_prefilter_find_and_group_candidates(self):
        srt_text = (
            "1\n00:00:01,000 --> 00:00:04,500\nSelamat datang di podcast ini.\n\n"
            "2\n00:00:05,000 --> 00:00:09,200\nPengalaman saya rugi omzet 100 juta itu luar biasa hancur.\n\n"
            "3\n00:00:10,000 --> 00:00:14,800\nTernyata kuncinya adalah bangkit dari nol dan ubah strategi bisnis."
        )
        candidates = find_candidates(srt_text, limit=10)
        self.assertGreater(len(candidates), 0)

        groups = group_candidates(candidates)
        self.assertGreater(len(groups), 0)

        prompt = build_gemini_prompt(groups, "https://youtube.com/watch?v=test")
        self.assertIn("ATURAN EVALUASI & VALIDASI", prompt)
        self.assertIn("https://youtube.com/watch?v=test", prompt)


if __name__ == "__main__":
    unittest.main()
