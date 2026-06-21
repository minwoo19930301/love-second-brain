# -*- coding: utf-8 -*-
"""
app/server.py build_context 단위 테스트.

RAG 프롬프트 발췌가 brain.search와 동일하게 한↔영 alias 확장을 적용하는지 검증한다.
표준라이브러리 unittest만 사용. (server import는 부작용 없음 — PORT는 env 폴백)
"""
import os
import sys
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "app"))

from test_brain import BrainFixtureTestCase, _write  # noqa: E402
import brain   # noqa: E402
import server  # noqa: E402


class TestBuildContext(BrainFixtureTestCase):
    def test_build_context_excerpt_uses_alias_expansion(self):
        # 한글 '여행' 질의 → 영문 'travel'만 있는 raw 문서의 발췌가
        # 파일 머리(text[:700])가 아니라 'travel' 매치 주변이어야 함
        body = "# Diary\n\n" + ("x" * 900) + "\nMARKER travel details"
        _write(os.path.join(self.raw, "trip.md"), body)
        wiki_hits, raw_hits = brain.search("여행")
        self.assertTrue(raw_hits)   # alias 확장으로 히트 자체는 성공해야 전제 성립
        ctx, citations = server.build_context(wiki_hits, raw_hits, "여행")
        self.assertIn("MARKER", ctx)
        self.assertIn("raw/trip.md", citations)


if __name__ == "__main__":
    unittest.main()
