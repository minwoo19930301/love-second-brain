# -*- coding: utf-8 -*-
"""
app/brain.py 검색 개선(F1~F4) 단위 테스트.

tempfile로 임시 wiki/raw 픽스처를 만들고 brain의 디렉토리 상수를 잠시 바꿔치기한다.
표준라이브러리 unittest만 사용.
"""
import os
import re
import sys
import shutil
import inspect
import tempfile
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "app"))
import brain  # noqa: E402


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _node_md(tldr="", tags=(), body="", verified=None, verified_by=None):
    """wiki 노드 마크다운 픽스처. verified/verified_by는 지정 시에만 frontmatter에 포함."""
    extra = ""
    if verified is not None:
        extra += "verified: %s\n" % verified
    if verified_by is not None:
        extra += "verified_by: %s\n" % verified_by
    return (
        "---\n"
        "type: concept\n"
        "tldr: %s\n"
        "tags: [%s]\n"
        "%s"
        "created: 2026-06-01\n"
        "updated: 2026-06-01\n"
        "---\n%s\n" % (tldr, ", ".join(tags), extra, body)
    )


class BrainFixtureTestCase(unittest.TestCase):
    """임시 BRAIN_DIR/WIKI_DIR/RAW_DIR 바꿔치기 공통 베이스 (tearDown 복원 + 캐시 clear)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="brain-test-")
        self.wiki = os.path.join(self.tmp, "wiki")
        self.raw = os.path.join(self.tmp, "raw")
        os.makedirs(self.wiki)
        os.makedirs(self.raw)
        self._orig_dirs = (brain.BRAIN_DIR, brain.WIKI_DIR, brain.RAW_DIR)
        brain.BRAIN_DIR, brain.WIKI_DIR, brain.RAW_DIR = self.tmp, self.wiki, self.raw
        getattr(brain, "_NODE_CACHE", {}).clear()
        getattr(brain, "_RAW_CACHE", {}).clear()

    def tearDown(self):
        brain.BRAIN_DIR, brain.WIKI_DIR, brain.RAW_DIR = self._orig_dirs
        getattr(brain, "_NODE_CACHE", {}).clear()
        getattr(brain, "_RAW_CACHE", {}).clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _count_reads(self, fn):
        """brain._read 호출 횟수를 세는 래퍼로 감싸고 fn 실행."""
        calls = {"n": 0}
        orig = brain._read

        def counting(path):
            calls["n"] += 1
            return orig(path)

        brain._read = counting
        try:
            out = fn()
        finally:
            brain._read = orig
        return calls["n"], out


# ---------------------------------------------------------------------------
# F1. mtime 증분 캐시
# ---------------------------------------------------------------------------
class TestIncrementalCache(BrainFixtureTestCase):
    def test_first_load_reads_all_then_reload_reads_zero(self):
        _write(os.path.join(self.wiki, "a.md"), _node_md("alpha", body="hello [[b]]"))
        _write(os.path.join(self.wiki, "sub", "b.md"), _node_md("beta", body="world"))
        n1, nodes1 = self._count_reads(brain.load_wiki_nodes)
        self.assertEqual(n1, 2)
        self.assertEqual(len(nodes1), 2)
        # 무변경 재로드 → _read 0회, 결과 동일
        n2, nodes2 = self._count_reads(brain.load_wiki_nodes)
        self.assertEqual(n2, 0)
        self.assertEqual(nodes1, nodes2)

    def test_modified_file_reparsed_once(self):
        pa = os.path.join(self.wiki, "a.md")
        _write(pa, _node_md("alpha"))
        _write(os.path.join(self.wiki, "b.md"), _node_md("beta"))
        brain.load_wiki_nodes()
        # 1파일만 수정 + mtime 명시 bump (mtime 해상도 이슈 회피)
        _write(pa, _node_md("alpha-v2"))
        st = os.stat(pa)
        os.utime(pa, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        n, nodes = self._count_reads(brain.load_wiki_nodes)
        self.assertEqual(n, 1)
        tldrs = {x["slug"]: x["tldr"] for x in nodes}
        self.assertEqual(tldrs["a"], "alpha-v2")
        self.assertEqual(tldrs["b"], "beta")

    def test_new_file_parsed_incrementally(self):
        _write(os.path.join(self.wiki, "a.md"), _node_md("alpha"))
        brain.load_wiki_nodes()
        _write(os.path.join(self.wiki, "c.md"), _node_md("gamma"))
        n, nodes = self._count_reads(brain.load_wiki_nodes)
        self.assertEqual(n, 1)
        self.assertEqual({x["slug"] for x in nodes}, {"a", "c"})

    def test_deleted_file_drops_out(self):
        pa = os.path.join(self.wiki, "a.md")
        _write(pa, _node_md("alpha"))
        _write(os.path.join(self.wiki, "b.md"), _node_md("beta"))
        brain.load_wiki_nodes()
        os.remove(pa)
        nodes = brain.load_wiki_nodes()
        self.assertEqual([x["slug"] for x in nodes], ["b"])

    def test_same_mtime_different_size_reparsed(self):
        # stamp의 size 성분 가드 — mtime이 같아도 크기가 다르면 재파싱해야 함
        pa = os.path.join(self.wiki, "a.md")
        _write(pa, _node_md("alpha"))
        st0 = os.stat(pa)
        brain.load_wiki_nodes()
        _write(pa, _node_md("alpha-much-longer"))            # 크기 변경
        os.utime(pa, ns=(st0.st_atime_ns, st0.st_mtime_ns))  # mtime 원복 → size로만 감지
        nodes = brain.load_wiki_nodes()
        self.assertEqual(nodes[0]["tldr"], "alpha-much-longer")


# ---------------------------------------------------------------------------
# raw 원본 증분 캐시 (warm search 이중 read 제거)
# ---------------------------------------------------------------------------
class TestRawCache(BrainFixtureTestCase):
    def test_cold_search_reads_each_raw_file_once(self):
        # list_raw_docs + 스코어링 루프의 이중 read 제거 — 파일당 1회만 read
        _write(os.path.join(self.raw, "a.md"), "# A\n\nsaturn body")
        _write(os.path.join(self.raw, "b.md"), "# B\n\nsaturn body")
        n, _ = self._count_reads(lambda: brain.search("saturn"))
        self.assertEqual(n, 2)

    def test_warm_search_reads_no_raw_files(self):
        _write(os.path.join(self.raw, "a.md"), "# A\n\nsaturn body")
        brain.search("saturn")   # cold: 캐시 적재
        n, out = self._count_reads(lambda: brain.search("saturn"))
        self.assertEqual(n, 0)   # warm: read 0회
        _, raw_hits = out
        self.assertEqual(len(raw_hits), 1)

    def test_modified_raw_doc_reflected(self):
        pa = os.path.join(self.raw, "a.md")
        _write(pa, "# A\n\nsaturn old-content")
        brain.search("saturn")
        _write(pa, "# A\n\nsaturn new-content")
        st = os.stat(pa)
        os.utime(pa, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))  # mtime 해상도 이슈 회피
        _, raw_hits = brain.search("saturn")
        self.assertIn("new-content", raw_hits[0][2])

    def test_same_mtime_different_size_raw_reparsed(self):
        # raw 캐시도 stamp에 size 성분 필수
        pa = os.path.join(self.raw, "a.md")
        _write(pa, "# A\n\nsaturn old")
        st0 = os.stat(pa)
        brain.search("saturn")
        _write(pa, "# A\n\nsaturn new-and-much-longer")
        os.utime(pa, ns=(st0.st_atime_ns, st0.st_mtime_ns))
        _, raw_hits = brain.search("saturn")
        self.assertIn("new-and-much-longer", raw_hits[0][2])


# ---------------------------------------------------------------------------
# F2. 한↔영 alias 질의 확장
# ---------------------------------------------------------------------------
class TestAliasExpansion(BrainFixtureTestCase):
    def test_expand_is_bidirectional(self):
        out = brain.expand_kws(["여행"])
        self.assertEqual(out[0], "여행")           # 원 토큰이 맨 앞 (순서 보존)
        self.assertIn("travel", out)
        self.assertIn("여행", brain.expand_kws(["travel"]))

    def test_expand_preserves_order_and_dedups(self):
        out = brain.expand_kws(["여행", "travel", "결혼"])
        self.assertEqual(len(out), len(set(out)))   # 중복 없음
        self.assertLess(out.index("여행"), out.index("결혼"))

    def test_unknown_token_passes_through(self):
        self.assertEqual(brain.expand_kws(["saturn"]), ["saturn"])

    def test_search_korean_query_hits_english_only_node(self):
        _write(os.path.join(self.wiki, "travel-plan.md"),
               _node_md("travel plan for our trip", body="travel itinerary details"))
        wiki_hits, _ = brain.search("여행 계획")
        self.assertIn("travel-plan", [n["slug"] for _, n in wiki_hits])

    def test_no_english_alias_shorter_than_3_chars(self):
        # substring 매칭이라 2글자 영문 alias("ad" 등)는 오탐 — 금지
        for group in brain.ALIAS_GROUPS:
            for w in group:
                if re.fullmatch(r"[a-z0-9_\-]+", w):
                    self.assertGreaterEqual(len(w), 3, "짧은 영문 alias 금지: %r" % w)

    def test_alias_groups_size(self):
        self.assertGreaterEqual(len(brain.ALIAS_GROUPS), 30)

    def test_cross_group_substring_alias_must_be_word_bounded(self):
        # 교차 그룹 substring 충돌(fee⊂feed, version⊂conversion)은 단어 경계 매칭
        # 대상(WORD_BOUNDED_ALIASES)으로 등록돼야 함 — 미등록 충돌은 오탐 발생
        flat = [(w, i) for i, g in enumerate(brain.ALIAS_GROUPS) for w in g]
        bad = [(a, b) for a, gi in flat for b, gj in flat
               if gi != gj and a != b and a in b and a not in brain.WORD_BOUNDED_ALIASES]
        self.assertEqual(bad, [], "교차 그룹 substring 충돌인데 단어 경계 매칭 미지정: %r" % bad)

    def test_fee_alias_does_not_hit_feed_only_node(self):
        # '수수료'→fee 확장이 'feed'만 있는 노드를 오탐하면 안 됨 (fee⊂feed)
        _write(os.path.join(self.wiki, "pcs-feed.md"),
               _node_md("PCS feed pipeline", body="feed processing details"))
        wiki_hits, _ = brain.search("수수료")
        self.assertEqual(wiki_hits, [])

    def test_fee_alias_does_not_hit_feed_only_raw_doc(self):
        _write(os.path.join(self.raw, "feed.md"), "# Feed Pipeline\n\nfeed processing notes")
        _, raw_hits = brain.search("수수료")
        self.assertEqual(raw_hits, [])

    def test_version_alias_does_not_hit_conversion_only_node(self):
        # '버전'→version 확장이 'conversion'만 있는 노드를 오탐하면 안 됨 (version⊂conversion)
        _write(os.path.join(self.wiki, "metrics.md"),
               _node_md("conversion metrics", body="conversion rate details"))
        wiki_hits, _ = brain.search("버전")
        self.assertEqual(wiki_hits, [])

    def test_word_bounded_alias_still_matches_compound_words(self):
        # 단어 경계 매칭이어도 하이픈/언더스코어 복합어('date-night')는 매칭 유지
        _write(os.path.join(self.wiki, "date-night.md"),
               _node_md("date-night plan", body="date_idea details"))
        wiki_hits, _ = brain.search("데이트")
        self.assertIn("date-night", [n["slug"] for _, n in wiki_hits])

    def test_excerpt_anchors_at_word_bounded_match(self):
        # 발췌 위치도 단어 경계 기준 — 'update' 안의 'date'가 아니라 진짜 'date' 주변
        text = "update log intro\n" + ("y" * 800) + "\nMARKER date night here"
        kws = brain.expand_kws(brain.tokenize("데이트"))
        out = brain.excerpt_around(text, kws, 400)
        self.assertIn("MARKER", out)


# ---------------------------------------------------------------------------
# F3. 그래프 1-hop 감쇠 점수
# ---------------------------------------------------------------------------
class TestGraphHop(BrainFixtureTestCase):
    def test_linked_neighbor_joins_with_decayed_score(self):
        _write(os.path.join(self.wiki, "hub.md"),
               _node_md("saturn version hub", body="saturn 설명. 관련: [[neighbor]]"))
        _write(os.path.join(self.wiki, "neighbor.md"),
               _node_md("totally unrelated", body="아무 관련 없는 본문"))
        wiki_hits, _ = brain.search("saturn")
        scores = {n["slug"]: s for s, n in wiki_hits}
        self.assertIn("neighbor", scores)
        self.assertAlmostEqual(scores["neighbor"], scores["hub"] * brain.GRAPH_HOP_DECAY)

    def test_dangling_link_ignored(self):
        _write(os.path.join(self.wiki, "hub.md"),
               _node_md("saturn hub", body="saturn 설명. [[ghost]] 링크"))
        wiki_hits, _ = brain.search("saturn")
        self.assertEqual([n["slug"] for _, n in wiki_hits], ["hub"])

    def test_already_hit_node_not_duplicated(self):
        _write(os.path.join(self.wiki, "hub.md"),
               _node_md("saturn hub", body="saturn 설명. [[other]] 링크"))
        _write(os.path.join(self.wiki, "other.md"),
               _node_md("saturn other", body="saturn 본문"))
        wiki_hits, _ = brain.search("saturn")
        slugs = [n["slug"] for _, n in wiki_hits]
        self.assertEqual(slugs.count("other"), 1)
        scores = {n["slug"]: s for s, n in wiki_hits}
        self.assertGreater(scores["other"], scores["hub"] * brain.GRAPH_HOP_DECAY)  # 자체 점수 유지

    def test_hop_results_respect_k_cut(self):
        # hub 1개 + 이웃 3개, k_wiki=2 → 합류 후에도 2개로 컷
        _write(os.path.join(self.wiki, "hub.md"),
               _node_md("saturn hub", body="saturn [[n1]] [[n2]] [[n3]]"))
        for s in ("n1", "n2", "n3"):
            _write(os.path.join(self.wiki, s + ".md"), _node_md("plain", body="plain"))
        wiki_hits, _ = brain.search("saturn", k_wiki=2)
        self.assertEqual(len(wiki_hits), 2)
        self.assertEqual(wiki_hits[0][1]["slug"], "hub")   # 부모가 최상위 유지

    def test_direct_hits_not_evicted_by_hop_neighbors(self):
        # 키워드를 실제 포함한 직접 히트는 hop-only(키워드 0회) 노드에 밀려 탈락하면 안 됨
        links = " ".join("[[n%d]]" % i for i in range(8))
        _write(os.path.join(self.wiki, "hub.md"),
               _node_md("saturn hub", tags=("saturn",), body="saturn " + links))  # 16점 허브
        for i in range(8):
            _write(os.path.join(self.wiki, "n%d.md" % i), _node_md("plain", body="plain"))
        for i in range(5):
            _write(os.path.join(self.wiki, "direct%d.md" % i),
                   _node_md("plain", body="saturn details"))                       # 3점 직접 히트
        wiki_hits, _ = brain.search("saturn", k_wiki=6)
        slugs = [n["slug"] for _, n in wiki_hits]
        self.assertEqual(len(wiki_hits), 6)
        self.assertIn("hub", slugs)
        for i in range(5):
            self.assertIn("direct%d" % i, slugs)   # 직접 히트 전원 생존

    def test_hop_expansion_limited_to_top5_hits(self):
        # 점수 엄격 감소(동점 플레이크 방지): slug+tldr+tags+body 조합으로 22/17/11/8/6/3
        _write(os.path.join(self.wiki, "saturn-a.md"), _node_md("saturn a", tags=("saturn",), body="saturn"))
        _write(os.path.join(self.wiki, "saturn-b.md"), _node_md("saturn b", body="saturn"))
        _write(os.path.join(self.wiki, "c.md"), _node_md("saturn c", body="saturn"))
        _write(os.path.join(self.wiki, "d.md"), _node_md("saturn d", body="plain"))
        _write(os.path.join(self.wiki, "saturn-e.md"), _node_md("plain", body="plain"))
        _write(os.path.join(self.wiki, "f.md"), _node_md("plain", body="saturn [[lucky]]"))  # 6위
        _write(os.path.join(self.wiki, "lucky.md"), _node_md("plain", body="plain"))
        wiki_hits, _ = brain.search("saturn")
        self.assertNotIn("lucky", [n["slug"] for _, n in wiki_hits])   # 6위 허브는 미확장

    def test_hop_is_one_hop_only(self):
        # 합류한 이웃의 링크는 재확장 금지 (1-hop 한정, multi-hop 금지)
        _write(os.path.join(self.wiki, "hub.md"), _node_md("saturn hub", body="saturn [[mid]]"))
        _write(os.path.join(self.wiki, "mid.md"), _node_md("plain mid", body="plain [[far]]"))
        _write(os.path.join(self.wiki, "far.md"), _node_md("plain far", body="plain"))
        wiki_hits, _ = brain.search("saturn")
        slugs = [n["slug"] for _, n in wiki_hits]
        self.assertIn("mid", slugs)
        self.assertNotIn("far", slugs)

    def test_shared_neighbor_decays_from_highest_parent_once(self):
        # 공유 이웃(부모 2개가 같은 [[링크]])은 최고점 부모 기준 1회만 감쇠 합류
        _write(os.path.join(self.wiki, "saturn-p1.md"), _node_md("saturn one", body="saturn [[shared]]"))  # 17점
        _write(os.path.join(self.wiki, "p2.md"), _node_md("plain", body="saturn [[shared]]"))              # 3점
        _write(os.path.join(self.wiki, "shared.md"), _node_md("plain shared", body="plain"))
        wiki_hits, _ = brain.search("saturn")
        self.assertEqual([n["slug"] for _, n in wiki_hits].count("shared"), 1)
        scores = {n["slug"]: s for s, n in wiki_hits}
        self.assertAlmostEqual(scores["shared"], scores["saturn-p1"] * brain.GRAPH_HOP_DECAY)


# ---------------------------------------------------------------------------
# F4. k 확대 (k_wiki 6→12, k_raw 5→10)
# ---------------------------------------------------------------------------
class TestSearchDefaults(BrainFixtureTestCase):
    def test_signature_defaults(self):
        sig = inspect.signature(brain.search)
        self.assertEqual(sig.parameters["k_wiki"].default, 12)
        self.assertEqual(sig.parameters["k_raw"].default, 10)

    def test_default_cut_behavior(self):
        for i in range(15):
            _write(os.path.join(self.wiki, "w%02d.md" % i), _node_md("saturn", body="saturn"))
        for i in range(12):
            _write(os.path.join(self.raw, "r%02d.md" % i), "# R%02d\n\nsaturn 내용" % i)
        wiki_hits, raw_hits = brain.search("saturn")
        self.assertEqual(len(wiki_hits), 12)
        self.assertEqual(len(raw_hits), 10)


# ---------------------------------------------------------------------------
# verified 검증 등급 — load 캡처 + 표시 헬퍼 (RAG 신뢰 노출)
# ---------------------------------------------------------------------------
class TestVerifiedField(BrainFixtureTestCase):
    def test_load_captures_verified_and_by(self):
        _write(os.path.join(self.wiki, "n.md"),
               _node_md("t", body="x", verified="domain-expert-verified", verified_by="한유미"))
        n = brain.load_wiki_nodes()[0]
        self.assertEqual(n["verified"], "domain-expert-verified")
        self.assertEqual(n["verified_by"], "한유미")

    def test_missing_verified_is_empty(self):
        # 레거시 노드(필드 없음) → "" — 깨지지 않고 미검증으로 취급
        _write(os.path.join(self.wiki, "legacy.md"), _node_md("t", body="x"))
        n = brain.load_wiki_nodes()[0]
        self.assertEqual(n["verified"], "")
        self.assertEqual(n["verified_by"], "")

    def test_verified_label_trusted(self):
        self.assertIn("code-verified", brain.verified_label({"verified": "code-verified"}))
        self.assertIn("한유미", brain.verified_label(
            {"verified": "domain-expert-verified", "verified_by": "한유미"}))

    def test_verified_label_untrusted_has_warning(self):
        self.assertIn("⚠", brain.verified_label({"verified": "provisional"}))
        self.assertIn("⚠", brain.verified_label({"verified": "unverified-capture"}))
        # 확인자 없는 expert·미정의 등급도 ⚠ (최상위 신뢰처럼 보이지 않게)
        self.assertIn("⚠", brain.verified_label({"verified": "domain-expert-verified"}))
        self.assertIn("⚠", brain.verified_label({"verified": "totally-verified"}))

    def test_verified_unmarked_is_neutral(self):
        # verified는 optional — 빈값(미부여)은 중립: label에 ⚠ 없음, tag는 빈 문자열
        self.assertNotIn("⚠", brain.verified_label({}))
        self.assertEqual(brain.verified_tag({}), "")

    def test_verified_none_is_safe(self):
        # None 입력 방어 — AttributeError 없이 중립 처리
        self.assertNotIn("⚠", brain.verified_label(None))
        self.assertEqual(brain.verified_tag(None), "")

    def test_verified_tag(self):
        self.assertEqual(brain.verified_tag({"verified": "code-verified"}), "code-verified")
        self.assertTrue(brain.verified_tag({"verified": "provisional"}).endswith("⚠"))
        self.assertEqual(brain.verified_tag({}), "")   # 미표기 → 중립(빈 태그)
        # 확인자 있는 expert는 신뢰(⚠ 없음), 없으면 ⚠
        self.assertEqual(brain.verified_tag(
            {"verified": "domain-expert-verified", "verified_by": "한유미"}), "domain-expert-verified")
        self.assertTrue(brain.verified_tag(
            {"verified": "domain-expert-verified"}).endswith("⚠"))


class TestMarkdownLinkExtraction(unittest.TestCase):
    """OKF: _extract_links가 표준 마크다운 링크 [text](path.md) + 레거시 [[ ]] 둘 다 인식."""

    def test_relative_md_link_becomes_edge(self):
        links = brain._extract_links("관련: [vip-coupon-kafka-recompute](vip-coupon-kafka-recompute.md)")
        self.assertEqual(links, [("vip-coupon-kafka-recompute", "extends")])

    def test_cross_folder_md_link_slug_is_basename(self):
        links = brain._extract_links("근거: supports [foo](../coupon/foo.md)")
        self.assertEqual(links, [("foo", "supports")])

    def test_legacy_wikilink_still_parsed(self):
        links = brain._extract_links("관련 [[neighbor]] 참고")
        self.assertEqual(links, [("neighbor", "extends")])

    def test_anchor_only_link_ignored(self):
        self.assertEqual(brain._extract_links("[§15](#15-gaps)"), [])

    def test_external_url_ignored(self):
        self.assertEqual(brain._extract_links("[blog](https://x.com/a.md)"), [])

    def test_non_md_prose_parenthetical_ignored(self):
        self.assertEqual(brain._extract_links("[미확인](설계 의도 확인 필요)"), [])

    def test_raw_targeting_md_link_is_not_an_edge(self):
        self.assertEqual(brain._extract_links("[x](../../raw/common/gmarket_common_infra.md)"), [])

    def test_image_embed_not_a_link(self):
        self.assertEqual(brain._extract_links("![diagram](pic.md)"), [])

    def test_aliased_md_link_uses_path_basename_as_slug(self):
        links = brain._extract_links("[OrgService](adm-org-snapshot-service.md)")
        self.assertEqual(links, [("adm-org-snapshot-service", "extends")])

    def test_proto_relative_url_ignored(self):
        self.assertEqual(brain._extract_links("[x](//cdn.example.com/a.md)"), [])

    def test_reserved_filename_not_an_edge(self):
        self.assertEqual(brain._extract_links("[log](log.md)"), [])
        self.assertEqual(brain._extract_links("[idx](index.md)"), [])


class TestTitleField(BrainFixtureTestCase):
    """OKF 표준 필드 title을 load_wiki_nodes가 노드 dict에 적재."""

    def test_title_captured_from_frontmatter(self):
        _write(os.path.join(self.wiki, "withtitle.md"),
               "---\ntype: claim\ntitle: My Title\ntldr: t\ntags: [x]\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n본문")
        n = next(n for n in brain.load_wiki_nodes() if n["slug"] == "withtitle")
        self.assertEqual(n["title"], "My Title")

    def test_title_defaults_to_empty_when_absent(self):
        _write(os.path.join(self.wiki, "notitle.md"),
               "---\ntype: claim\ntldr: t\ntags: [x]\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n본문")
        n = next(n for n in brain.load_wiki_nodes() if n["slug"] == "notitle")
        self.assertEqual(n["title"], "")


if __name__ == "__main__":
    unittest.main()
