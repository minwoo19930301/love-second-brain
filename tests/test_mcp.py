# -*- coding: utf-8 -*-
"""
mcp-server/brain_mcp.py 검색 도구(F4) 단위 테스트.

tool_search_brain(dict)을 직접 호출해 출력 문자열을 검증한다. 표준라이브러리 unittest만 사용.
"""
import os
import sys
import shutil
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "app"))
sys.path.insert(0, os.path.join(_REPO, "mcp-server"))
import brain      # noqa: E402
import brain_mcp  # noqa: E402


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _node_md(tldr="", body=""):
    return "---\ntype: concept\ntldr: %s\ntags: []\n---\n%s\n" % (tldr, body)


class McpFixtureTestCase(unittest.TestCase):
    """임시 BRAIN_DIR/WIKI_DIR/RAW_DIR 바꿔치기 (brain_mcp는 brain 모듈을 공유)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="brain-mcp-test-")
        self.wiki = os.path.join(self.tmp, "wiki")
        self.raw = os.path.join(self.tmp, "raw")
        os.makedirs(self.wiki)
        os.makedirs(self.raw)
        self._orig_dirs = (brain.BRAIN_DIR, brain.WIKI_DIR, brain.RAW_DIR)
        brain.BRAIN_DIR, brain.WIKI_DIR, brain.RAW_DIR = self.tmp, self.wiki, self.raw
        brain._NODE_CACHE.clear()
        getattr(brain, "_RAW_CACHE", {}).clear()

    def tearDown(self):
        brain.BRAIN_DIR, brain.WIKI_DIR, brain.RAW_DIR = self._orig_dirs
        brain._NODE_CACHE.clear()
        getattr(brain, "_RAW_CACHE", {}).clear()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestSearchBrainTool(McpFixtureTestCase):
    def test_schema_limit_default_is_12(self):
        tool = next(t for t in brain_mcp.TOOLS if t["name"] == "search_brain")
        self.assertEqual(tool["inputSchema"]["properties"]["limit"]["default"], 12)

    def test_default_limit_returns_up_to_12_wiki(self):
        for i in range(13):
            _write(os.path.join(self.wiki, "w%02d.md" % i), _node_md("saturn", "saturn"))
        out = brain_mcp.tool_search_brain({"query": "saturn"})
        self.assertIn("## wiki 정제 노드 (12)", out)

    def test_raw_tail_has_no_excerpt_after_top5(self):
        # 7개 raw 문서, 키워드 빈도로 순위 고정 (r1 최다 → 1위)
        for i in range(1, 8):
            body = "# R%d\n\n%s" % (i, "saturn " * (20 - i))
            _write(os.path.join(self.raw, "r%d.md" % i), body)
        out = brain_mcp.tool_search_brain({"query": "saturn"})
        raw_section = out.split("## raw 원본 발췌")[1]
        items = [l for l in raw_section.split("\n") if l.strip() and l.strip()[0].isdigit()]
        self.assertEqual(len(items), 7)
        excerpt_lines = [l for l in raw_section.split("\n") if l.strip().startswith(">")]
        # 상위 RAW_EXCERPT_TOP(5)만 발췌, 6위~는 제목+path만
        self.assertEqual(len(excerpt_lines), brain_mcp.RAW_EXCERPT_TOP)
        self.assertEqual(brain_mcp.RAW_EXCERPT_TOP, 5)

    def test_excerpt_uses_alias_expanded_kws(self):
        # 한글 질의 '여행' → 영문만 있는 문서에서 'travel' 주변이 발췌돼야 함
        body = "# Diary\n\n" + ("x" * 600) + "\nMARKER travel details"
        _write(os.path.join(self.raw, "trip.md"), body)
        out = brain_mcp.tool_search_brain({"query": "여행"})
        self.assertIn("MARKER", out)

    def test_wiki_output_format_kept(self):
        _write(os.path.join(self.wiki, "saturn.md"), _node_md("saturn tldr", "saturn"))
        out = brain_mcp.tool_search_brain({"query": "saturn"})
        self.assertIn("**saturn** — saturn tldr", out)   # tldr 유지
        self.assertIn("path: `wiki/saturn.md`", out)     # path 유지

    def test_main_warms_up_node_cache(self):
        # 기동 warm-up: main()이 load_wiki_nodes()를 '실제 호출'하는지 행동 검증
        # (소스 문자열 검사는 호출을 주석처리해도 통과 — 호출 횟수로 확인)
        import io
        called = {"n": 0}
        orig_load, orig_stdin, orig_stderr = brain.load_wiki_nodes, sys.stdin, sys.stderr

        def counting():
            called["n"] += 1
            return orig_load()

        brain.load_wiki_nodes = counting
        sys.stdin = io.StringIO("")     # 빈 stdin → main 루프 즉시 종료
        sys.stderr = io.StringIO()      # 기동 로그 출력 억제
        try:
            brain_mcp.main()
        finally:
            brain.load_wiki_nodes = orig_load
            sys.stdin = orig_stdin
            sys.stderr = orig_stderr
        self.assertGreaterEqual(called["n"], 1)


class TestVerifiedSurfacing(McpFixtureTestCase):
    """verified 등급이 get_node·search_brain·list_nodes·brain_overview에 노출되는지."""

    def _vnode(self, slug, verified, verified_by=None, tldr="saturn", body="saturn"):
        fm = "---\ntype: concept\ntldr: %s\ntags: [domain/test]\nverified: %s\n" % (tldr, verified)
        if verified_by is not None:
            fm += "verified_by: %s\n" % verified_by
        fm += "---\n%s\n" % body
        _write(os.path.join(self.wiki, slug + ".md"), fm)

    def test_get_node_shows_verified_label(self):
        self._vnode("expert", "domain-expert-verified", verified_by="한유미", body="[[expert]] 자기참조.")
        out = brain_mcp.tool_get_node({"slug": "expert"})
        self.assertIn("verified:", out)
        self.assertIn("domain-expert-verified", out)
        self.assertIn("한유미", out)

    def test_get_node_warns_on_provisional(self):
        self._vnode("guess", "provisional", body="[[guess]] 자기참조.")
        out = brain_mcp.tool_get_node({"slug": "guess"})
        self.assertIn("⚠", out)

    def test_search_brain_tags_low_trust_on_that_line(self):
        # 명시적 저신뢰(provisional) 노드 → 그 노드 줄 태그에 ⚠ (푸터가 아닌 노드 줄에서 확인)
        self._vnode("saturn", "provisional")
        out = brain_mcp.tool_search_brain({"query": "saturn"})
        line = next(l for l in out.split("\n") if "**saturn**" in l)
        self.assertIn("⚠", line)

    def test_search_brain_unmarked_is_neutral(self):
        # 등급 미표기(optional) → 중립: 노드 줄·푸터 어디에도 ⚠ 없음
        _write(os.path.join(self.wiki, "saturn.md"), _node_md("saturn", "saturn"))
        out = brain_mcp.tool_search_brain({"query": "saturn"})
        self.assertNotIn("⚠", out)

    def test_search_brain_trusted_no_warning_on_that_line(self):
        self._vnode("saturn", "code-verified")
        out = brain_mcp.tool_search_brain({"query": "saturn"})
        line = next(l for l in out.split("\n") if "**saturn**" in l)
        self.assertIn("code-verified", line)
        self.assertNotIn("⚠", line)

    def test_list_nodes_shows_verified_tag(self):
        self._vnode("saturn", "code-verified")
        out = brain_mcp.tool_list_nodes({})
        self.assertIn("code-verified", out)

    def test_brain_overview_shows_verified_distribution(self):
        self._vnode("a", "code-verified")
        self._vnode("b", "provisional")
        out = brain_mcp.tool_brain_overview({})
        self.assertIn("검증 등급", out)
        self.assertIn("code-verified", out)
        self.assertIn("provisional", out)


if __name__ == "__main__":
    unittest.main()
