# -*- coding: utf-8 -*-
"""
scripts/parse_kakao.py 단위 테스트. 표준라이브러리 unittest만 사용.
"""
import os
import sys
import shutil
import tempfile
import unittest
import datetime

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))
import parse_kakao as pk  # noqa: E402


def setUpModule():
    # 본인 이름은 평소 환경변수 SB_ME_NAMES로 지정 — 테스트에서는 고정값 주입.
    pk.ME_NAMES = {"홍길동"}


SAMPLE_A = """﻿Talk_2019.txt
저장한 날짜 : 2020. 6. 4. 오후 2:53


2019년 5월 7일 화요일
2019. 5. 7. 오전 10:16, 홍길동 : 오늘 점심 먹을래?
2019. 5. 7. 오전 10:17, 그대 : 헉 저 오늘은 약속있어여 ㅠㅠ
2019. 5. 7. 오후 8:39, 홍길동 : 여러 줄
이건 둘째 줄
2019년 5월 8일 수요일
2019. 5. 8. 오전 12:05, 그대 : 자정 메시지
"""

# B는 A와 한 메시지가 겹침(2019-05-07 10:16 홍길동) + 신규 1건
SAMPLE_B = """﻿Talk_later.txt
저장한 날짜 : 2026. 6. 5. 오후 4:44


2019년 5월 7일 화요일
2019. 5. 7. 오전 10:16, 홍길동 : 오늘 점심 먹을래?
2020년 10월 10일 토요일
2020. 10. 10. 오후 7:55, 그대 : 벌써 보고싶어
"""


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestTimeConvert(unittest.TestCase):
    def test_am_pm(self):
        self.assertEqual(pk.to_24h("오전", 12), 0)    # 자정
        self.assertEqual(pk.to_24h("오전", 10), 10)
        self.assertEqual(pk.to_24h("오후", 12), 12)   # 정오
        self.assertEqual(pk.to_24h("오후", 1), 13)
        self.assertEqual(pk.to_24h("오후", 11), 23)


class TestSender(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(pk.normalize_sender("홍길동"), pk.ME)       # 본인(ME_NAMES)
        self.assertEqual(pk.normalize_sender("그대"), pk.WIFE)       # 그 외는 모두 상대
        self.assertEqual(pk.normalize_sender("아무개"), pk.WIFE)     # 1:1이라 상대는 모두 '아내'


class TestIterMessages(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_parse_and_multiline(self):
        p = os.path.join(self.d, "a.txt")
        _write(p, SAMPLE_A)
        msgs = list(pk.iter_messages(p))
        self.assertEqual(len(msgs), 4)
        dt0, s0, t0 = msgs[0]
        self.assertEqual((dt0.year, dt0.month, dt0.day, dt0.hour, dt0.minute), (2019, 5, 7, 10, 16))
        self.assertEqual(s0, "홍길동")
        # 멀티라인 병합
        multi = next(t for _, _, t in msgs if "여러 줄" in t)
        self.assertIn("이건 둘째 줄", multi)
        # 오전 12시 → 0시
        midnight = next(dt for dt, _, t in msgs if "자정" in t)
        self.assertEqual(midnight.hour, 0)


class TestCollectDedup(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_cross_file_dedup_and_sort(self):
        fa, fb = os.path.join(self.d, "fa"), os.path.join(self.d, "fb")
        _write(os.path.join(fa, "Talk-1.txt"), SAMPLE_A)
        _write(os.path.join(fb, "Talk-1.txt"), SAMPLE_B)
        msgs, files, dup = pk.collect([fa, fb])
        self.assertEqual(len(files), 2)
        self.assertEqual(dup, 1)                       # 겹친 1건 제거
        # 정규화 발신자
        senders = {s for _, s, _, _ in msgs}
        self.assertEqual(senders, {pk.ME, pk.WIFE})
        # 시각 오름차순 정렬
        dts = [m[0] for m in msgs]
        self.assertEqual(dts, sorted(dts))
        # 2020-10 신규 메시지 포함
        self.assertTrue(any(d.year == 2020 and d.month == 10 for d, _, _, _ in msgs))


class TestWriteEndToEnd(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._orig_out = pk.OUT_DIR
        pk.OUT_DIR = os.path.join(self.d, "chat")

    def tearDown(self):
        pk.OUT_DIR = self._orig_out
        shutil.rmtree(self.d, ignore_errors=True)

    def test_writes_month_files_and_manifest(self):
        src = os.path.join(self.d, "src")
        _write(os.path.join(src, "Talk-1.txt"), SAMPLE_A)
        rc = pk.main(["parse_kakao.py", src])
        self.assertEqual(rc, 0)
        f = os.path.join(pk.OUT_DIR, "2019", "2019-05.md")
        self.assertTrue(os.path.isfile(f))
        with open(f, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("# 2019년 5월 카카오톡 대화", body)
        self.assertIn("10:16 나: 오늘 점심", body)
        self.assertIn("00:05 아내: 자정 메시지", body)   # 24h 변환 확인
        self.assertTrue(os.path.isfile(os.path.join(pk.OUT_DIR, "manifest.md")))
        self.assertTrue(os.path.isfile(os.path.join(pk.OUT_DIR, "README.md")))


if __name__ == "__main__":
    unittest.main()
