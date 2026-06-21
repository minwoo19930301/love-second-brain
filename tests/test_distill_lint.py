# -*- coding: utf-8 -*-
"""
scripts/distill_lint.py strict lint 단위 테스트.

tempfile로 임시 wiki/raw 픽스처를 만들고 brain의 디렉토리 상수를 잠시 바꿔치기한다.
(distill_lint는 brain 모듈을 공유하므로 패치가 그대로 반영된다.)
표준라이브러리 unittest만 사용.
"""
import io
import os
import sys
import shutil
import tempfile
import unittest
import contextlib
import subprocess

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "app"))
sys.path.insert(0, os.path.join(_REPO, "scripts"))
import brain         # noqa: E402
import distill_lint  # noqa: E402


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _node_md(ntype="claim", title='"테스트 제목 test title"', tldr='"테스트 주장 test claim"', tags="[domain/test]",
             sources='[{platform: repo, url: "x/y.kt", date: "2026-06-12"}]',
             verified="unverified-capture", verified_by=None,
             body="본문. [[hub]] 참고.", omit=()):
    """frontmatter 필드를 선택적으로 빼거나 바꿀 수 있는 노드 픽스처."""
    lines = ["---"]
    if "type" not in omit:
        lines.append("type: %s" % ntype)
    if "title" not in omit:
        lines.append("title: %s" % title)
    if "tldr" not in omit:
        lines.append("tldr: %s" % tldr)
    if "tags" not in omit:
        lines.append("tags: %s" % tags)
    if "sources" not in omit:
        lines.append("sources: %s" % sources)
    if "verified" not in omit:
        lines.append("verified: %s" % verified)
    if verified_by is not None and "verified_by" not in omit:
        lines.append("verified_by: %s" % verified_by)
    lines.append("created: 2026-06-12")
    lines.append("updated: 2026-06-12")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body + "\n"


class LintFixtureTestCase(unittest.TestCase):
    """임시 BRAIN_DIR/WIKI_DIR/RAW_DIR 바꿔치기 공통 베이스 (tearDown 복원 + 캐시 clear)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="distill-lint-test-")
        self.wiki = os.path.join(self.tmp, "wiki")
        self.raw = os.path.join(self.tmp, "raw")
        os.makedirs(self.wiki)
        os.makedirs(self.raw)
        self._orig_dirs = (brain.BRAIN_DIR, brain.WIKI_DIR, brain.RAW_DIR)
        brain.BRAIN_DIR, brain.WIKI_DIR, brain.RAW_DIR = self.tmp, self.wiki, self.raw
        getattr(brain, "_NODE_CACHE", {}).clear()
        getattr(brain, "_RAW_CACHE", {}).clear()
        # 링크 타깃용 hub 노드 (corpus 존재 제공 — 전체 스캔 시에도 위반 0이어야 함)
        _write(os.path.join(self.wiki, "hub.md"), _node_md(body="허브. [[hub]] 자기참조."))

    def tearDown(self):
        brain.BRAIN_DIR, brain.WIKI_DIR, brain.RAW_DIR = self._orig_dirs
        getattr(brain, "_NODE_CACHE", {}).clear()
        getattr(brain, "_RAW_CACHE", {}).clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _lint(self, *paths):
        return distill_lint.lint_files(list(paths))

    def _main(self, argv):
        """main() 실행 — (exit_code, stdout) 반환."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = distill_lint.main(argv)
        return code, buf.getvalue()


# ---------------------------------------------------------------------------
# 정상 노드 통과
# ---------------------------------------------------------------------------
class TestValidNode(LintFixtureTestCase):
    def test_valid_node_passes(self):
        p = os.path.join(self.wiki, "valid-node.md")
        _write(p, _node_md())
        self.assertEqual(self._lint(p), [])
        code, out = self._main([p])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_all_six_types_accepted(self):
        for ntype in brain.NODE_TYPES:
            # 모든 타입이 본문 [[링크]]≥1만 있으면 통과 (decision도 supports 형식 비강제)
            p = os.path.join(self.wiki, "node-%s.md" % ntype)
            _write(p, _node_md(ntype=ntype, body="본문. [[hub]] 참고."))
            self.assertEqual(self._lint(p), [], "type=%s 정상 노드가 실패함" % ntype)


# ---------------------------------------------------------------------------
# 위반 1. type — NODE_TYPES 6종 밖 (빈 값/누락 포함)
# ---------------------------------------------------------------------------
class TestTypeViolation(LintFixtureTestCase):
    def test_unknown_type_fails(self):
        p = os.path.join(self.wiki, "bad-type.md")
        _write(p, _node_md(ntype="bug-pattern"))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("type", violations[0][1])

    def test_missing_type_fails(self):
        p = os.path.join(self.wiki, "no-type.md")
        _write(p, _node_md(omit=("type",)))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("type", violations[0][1])

    def test_no_frontmatter_fails(self):
        p = os.path.join(self.wiki, "no-fm.md")
        _write(p, "frontmatter 없는 본문만 있는 파일.\n")
        violations = self._lint(p)
        reasons = " / ".join(r for _, r in violations)
        self.assertIn("type", reasons)


# ---------------------------------------------------------------------------
# 위반 2. tldr — 빈 값/누락
# ---------------------------------------------------------------------------
class TestTldrViolation(LintFixtureTestCase):
    def test_empty_tldr_fails(self):
        p = os.path.join(self.wiki, "empty-tldr.md")
        _write(p, _node_md(tldr='""'))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("tldr", violations[0][1])

    def test_missing_tldr_fails(self):
        p = os.path.join(self.wiki, "no-tldr.md")
        _write(p, _node_md(omit=("tldr",)))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("tldr", violations[0][1])


# ---------------------------------------------------------------------------
# 위반 3. tags — 비리스트 또는 빈 리스트
# ---------------------------------------------------------------------------
class TestTagsViolation(LintFixtureTestCase):
    def test_empty_tags_fails(self):
        p = os.path.join(self.wiki, "empty-tags.md")
        _write(p, _node_md(tags="[]"))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("tags", violations[0][1])

    def test_non_list_tags_fails(self):
        p = os.path.join(self.wiki, "scalar-tags.md")
        _write(p, _node_md(tags="domain/test"))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("tags", violations[0][1])


# ---------------------------------------------------------------------------
# 위반 4. sources — 누락/빈 리스트/항목이 dict 아님 (distill 강화 규칙)
# ---------------------------------------------------------------------------
class TestSourcesViolation(LintFixtureTestCase):
    def test_missing_sources_fails(self):
        p = os.path.join(self.wiki, "no-sources.md")
        _write(p, _node_md(omit=("sources",)))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("sources", violations[0][1])

    def test_empty_sources_fails(self):
        p = os.path.join(self.wiki, "empty-sources.md")
        _write(p, _node_md(sources="[]"))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("sources", violations[0][1])

    def test_non_dict_source_item_fails(self):
        p = os.path.join(self.wiki, "str-sources.md")
        _write(p, _node_md(sources='["그냥 문자열 출처"]'))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("sources", violations[0][1])


# ---------------------------------------------------------------------------
# 위반 5. dangling [[링크]] — 타깃 slug가 corpus(+lint 대상)에 없음
# ---------------------------------------------------------------------------
class TestDanglingLink(LintFixtureTestCase):
    def test_dangling_link_fails(self):
        p = os.path.join(self.wiki, "dangling.md")
        _write(p, _node_md(body="없는 노드 [[ghost-node]] 참조."))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("ghost-node", violations[0][1])

    def test_link_to_colinted_new_file_passes(self):
        # 같은 lint 호출에 함께 들어온 신규 파일끼리의 상호 링크는 dangling 아님.
        # corpus(wiki/) 밖 경로여야 "co-lint 합집합" 기능 자체를 실검증한다 —
        # wiki/ 안에 쓰면 corpus 스캔만으로 통과해 버려 명목 테스트가 됨.
        pa = os.path.join(self.tmp, "staging", "new-a.md")
        pb = os.path.join(self.tmp, "staging", "new-b.md")
        _write(pa, _node_md(body="[[new-b]] 참고."))
        _write(pb, _node_md(body="[[new-a]] 참고."))
        self.assertEqual(self._lint(pa, pb), [])

    def test_missing_input_path_does_not_suppress_dangling(self):
        # 미존재 입력 경로는 "경로 없음" 위반으로 보고되고, 그 slug는
        # known_slugs에 합산되지 않아야 한다 (dangling 억제 금지).
        p = os.path.join(self.wiki, "linker.md")
        _write(p, _node_md(body="없는 노드 [[ghost-node]] 참조."))
        ghost = os.path.join(self.wiki, "ghost-node.md")   # 실제로 만들지 않음
        violations = self._lint(p, ghost)
        reasons = [r for _, r in violations]
        self.assertTrue(any("존재하지 않" in r for r in reasons), violations)
        self.assertTrue(any("dangling" in r and "ghost-node" in r for r in reasons),
                        "미존재 입력 경로가 dangling 판정을 억제함: %r" % violations)

    def test_link_with_label_and_anchor_resolved(self):
        p = os.path.join(self.wiki, "label-link.md")
        _write(p, _node_md(body="[[hub|허브 노드]] 그리고 [[hub#섹션]] 참고."))
        self.assertEqual(self._lint(p), [])


# ---------------------------------------------------------------------------
# 위반 6. 중복 slug — 같은 slug의 다른 파일이 wiki에 이미 존재
# ---------------------------------------------------------------------------
class TestDuplicateSlug(LintFixtureTestCase):
    def test_duplicate_slug_fails(self):
        _write(os.path.join(self.wiki, "discount", "same-slug.md"), _node_md())
        p = os.path.join(self.wiki, "coupon", "same-slug.md")
        _write(p, _node_md())
        violations = self._lint(p)
        self.assertEqual(len(violations), 1)
        self.assertIn("slug", violations[0][1])

    def test_self_is_not_duplicate(self):
        p = os.path.join(self.wiki, "unique-slug.md")
        _write(p, _node_md())
        self.assertEqual(self._lint(p), [])

    def test_duplicate_slug_within_batch_fails(self):
        # corpus 밖 경로로 co-lint된 동일 slug 파일 쌍도 중복으로 검출해야 한다
        pa = os.path.join(self.tmp, "staging-1", "same-slug.md")
        pb = os.path.join(self.tmp, "staging-2", "same-slug.md")
        _write(pa, _node_md())
        _write(pb, _node_md())
        violations = self._lint(pa, pb)
        dup = [v for v in violations if "slug" in v[1]]
        self.assertEqual(len(dup), 2, "배치 내 동일 slug 쌍 미검출: %r" % violations)


# ---------------------------------------------------------------------------
# decision 노드 — 근거 링크는 필수(검사 8: 링크≥1)이나 supports '형식'은 권장(비강제)
# schema.md §엣지: "관계 표기는 권장". 근거 자체는 [[링크]]≥1로 충족되면 된다.
# ---------------------------------------------------------------------------
class TestDecisionSupports(LintFixtureTestCase):
    def test_decision_without_supports_passes(self):
        # supports 형식 없이 본문에 근거 [[링크]]만 있어도 통과 (schema 권장 정신)
        p = os.path.join(self.wiki, "bare-decision.md")
        _write(p, _node_md(ntype="decision", body="결정 근거는 [[hub]] 참고."))
        self.assertEqual(self._lint(p), [])

    def test_decision_with_supports_passes(self):
        # supports로 명시해도 통과 (권장 형식)
        p = os.path.join(self.wiki, "good-decision.md")
        _write(p, _node_md(ntype="decision", body="## 근거\n- supports: [[hub]]\n"))
        self.assertEqual(self._lint(p), [])

    def test_decision_prose_link_passes(self):
        # prose 안의 [[링크]] 근거도 통과 (형식 강제 안 함)
        p = os.path.join(self.wiki, "prose-decision.md")
        _write(p, _node_md(ntype="decision",
                           body="이 결정의 근거는 [[hub]] 참고."))
        self.assertEqual(self._lint(p), [])

    def test_decision_without_any_link_fails_by_link_rule(self):
        # 링크가 아예 없으면 검사 8(링크≥1)로 실패 — supports와 무관
        p = os.path.join(self.wiki, "linkless-decision.md")
        _write(p, _node_md(ntype="decision", body="링크 없는 결정 본문."))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("링크", violations[0][1])


# ---------------------------------------------------------------------------
# 위반 8. 본문 [[링크]] ≥ 1 — distill 강화 규칙 (0개면 실패)
# ---------------------------------------------------------------------------
class TestLinkRequired(LintFixtureTestCase):
    def test_node_without_links_fails(self):
        p = os.path.join(self.wiki, "no-links.md")
        _write(p, _node_md(body="링크가 하나도 없는 본문."))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("링크", violations[0][1])

    def test_node_with_one_link_passes(self):
        p = os.path.join(self.wiki, "one-link.md")
        _write(p, _node_md(body="[[hub]] 하나면 충분."))
        self.assertEqual(self._lint(p), [])


# ---------------------------------------------------------------------------
# 위반 9. sources의 raw/·wiki/ 상대경로 실존 검사 (http(s) 외부 URL 제외)
# ---------------------------------------------------------------------------
class TestSourcePathExists(LintFixtureTestCase):
    def test_missing_raw_source_path_fails(self):
        p = os.path.join(self.wiki, "ghost-raw-src.md")
        _write(p, _node_md(
            sources='[{platform: raw, url: "raw/test/ghost.md", date: "2026-06-12"}]'))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("raw/test/ghost.md", violations[0][1])

    def test_existing_raw_source_path_passes(self):
        _write(os.path.join(self.raw, "test", "real.md"), "원본.\n")
        p = os.path.join(self.wiki, "real-raw-src.md")
        _write(p, _node_md(
            sources='[{platform: raw, url: "raw/test/real.md", date: "2026-06-12"}]'))
        self.assertEqual(self._lint(p), [])

    def test_missing_wiki_source_path_key_fails(self):
        # url 외 path 키도 동일하게 검사
        p = os.path.join(self.wiki, "ghost-wiki-src.md")
        _write(p, _node_md(
            sources='[{platform: wiki, path: "wiki/none/ghost.md", date: "2026-06-12"}]'))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("wiki/none/ghost.md", violations[0][1])

    def test_external_http_url_not_checked(self):
        p = os.path.join(self.wiki, "http-src.md")
        _write(p, _node_md(
            sources='[{platform: confluence, url: "https://wiki.gmarket.com/x", date: "2026-06-12"}]'))
        self.assertEqual(self._lint(p), [])

    def test_repo_style_source_not_checked(self):
        # raw/·wiki/로 시작하지 않는 repo 경로 표기는 실존 검사 대상 아님
        p = os.path.join(self.wiki, "repo-src.md")
        _write(p, _node_md(
            sources='[{platform: repo, url: "some-repo/src/Main.kt", date: "2026-06-12"}]'))
        self.assertEqual(self._lint(p), [])

    def test_missing_node_relative_source_path_fails(self):
        # corpus 관례인 ../../raw/... 노드 상대경로 — 깨진 경로 검출 (SKILL 회의록 행 표기)
        p = os.path.join(self.wiki, "crawl", "rel-ghost-src.md")
        _write(p, _node_md(
            sources='[{platform: raw, url: "../../raw/crawl/ghost.md", date: "2026-06-12"}]'))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("../../raw/crawl/ghost.md", violations[0][1])

    def test_existing_node_relative_source_path_passes(self):
        _write(os.path.join(self.raw, "crawl", "memo.md"), "원본.\n")
        p = os.path.join(self.wiki, "crawl", "rel-real-src.md")
        _write(p, _node_md(
            sources='[{platform: raw, url: "../../raw/crawl/memo.md", date: "2026-06-12"}]'))
        self.assertEqual(self._lint(p), [])


# ---------------------------------------------------------------------------
# 위반 9/10. verified — (선택) 있을 때 enum 검사 + domain-expert-verified의 verified_by 의무
# ---------------------------------------------------------------------------
class TestVerifiedViolation(LintFixtureTestCase):
    def test_missing_verified_passes(self):
        # verified는 선택 필드 — 없어도 통과(optional). 등급을 항상 다는 건 distill 절차의 몫.
        p = os.path.join(self.wiki, "no-verified.md")
        _write(p, _node_md(omit=("verified",)))
        self.assertEqual(self._lint(p), [])

    def test_empty_verified_value_passes(self):
        # 빈 `verified:` (템플릿 기본값 = 중립 시작) → 파서가 []로 읽어도 통과해야 함
        p = os.path.join(self.wiki, "empty-verified.md")
        _write(p, _node_md(verified=""))
        self.assertEqual(self._lint(p), [])

    def test_invalid_verified_value_fails(self):
        p = os.path.join(self.wiki, "bad-verified.md")
        _write(p, _node_md(verified="totally-verified"))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("verified", violations[0][1])

    def test_all_verified_levels_pass(self):
        for lvl in distill_lint.VERIFIED_LEVELS:
            vby = '"한유미"' if lvl == "domain-expert-verified" else None
            p = os.path.join(self.wiki, "v-%s.md" % lvl)
            _write(p, _node_md(verified=lvl, verified_by=vby))
            self.assertEqual(self._lint(p), [], "verified=%s 정상 노드가 실패함" % lvl)

    def test_domain_expert_verified_requires_verified_by(self):
        p = os.path.join(self.wiki, "expert-no-by.md")
        _write(p, _node_md(verified="domain-expert-verified"))  # verified_by 없음
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("verified_by", violations[0][1])

    def test_domain_expert_verified_with_verified_by_passes(self):
        p = os.path.join(self.wiki, "expert-with-by.md")
        _write(p, _node_md(verified="domain-expert-verified", verified_by='"한유미"'))
        self.assertEqual(self._lint(p), [])

    def test_empty_verified_by_fails(self):
        p = os.path.join(self.wiki, "expert-empty-by.md")
        _write(p, _node_md(verified="domain-expert-verified", verified_by='""'))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("verified_by", violations[0][1])

    def test_verified_by_not_required_for_other_levels(self):
        # provisional/code-verified/unverified-capture는 verified_by 없어도 통과
        p = os.path.join(self.wiki, "provisional-node.md")
        _write(p, _node_md(verified="provisional"))
        self.assertEqual(self._lint(p), [])

    def test_inline_comment_on_verified_normalized(self):
        # verified 값 뒤 inline '#' 주석은 정규화 후 enum 검사 → 통과 (템플릿 복사 케이스)
        p = os.path.join(self.wiki, "verified-inline-comment.md")
        _write(p, _node_md(verified="code-verified   # 코드 대조함"))
        self.assertEqual(self._lint(p), [])

    def test_comment_only_verified_by_fails(self):
        # domain-expert-verified인데 verified_by에 주석만 남으면 (파서가 값으로 읽어도) 불인정
        p = os.path.join(self.wiki, "expert-comment-by.md")
        _write(p, _node_md(verified="domain-expert-verified", verified_by="# 한유미"))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("verified_by", violations[0][1])


# ---------------------------------------------------------------------------
# CLI 동작 — 인자 없으면 wiki/ 전체, exit code, 존재하지 않는 파일
# ---------------------------------------------------------------------------
class TestCli(LintFixtureTestCase):
    def test_no_args_lints_whole_wiki(self):
        _write(os.path.join(self.wiki, "bad.md"), _node_md(ntype="bug-pattern"))
        code, out = self._main([])
        self.assertEqual(code, 1)
        self.assertIn("bad.md", out)
        # hub.md(정상)는 위반으로 안 나옴
        self.assertNotIn("hub.md:", out)

    def test_violation_output_format(self):
        p = os.path.join(self.wiki, "empty-tldr.md")
        _write(p, _node_md(tldr='""'))
        code, out = self._main([p])
        self.assertEqual(code, 1)
        # "경로: 사유" 형식
        self.assertRegex(out, r"empty-tldr\.md: .*tldr")

    def test_missing_file_fails(self):
        code, out = self._main([os.path.join(self.wiki, "no-such-file.md")])
        self.assertEqual(code, 1)


class TestCliSubprocess(unittest.TestCase):
    """실제 CLI를 subprocess로 실행해 exit code 검증 (실 repo wiki corpus 기준)."""

    SCRIPT = os.path.join(_REPO, "scripts", "distill_lint.py")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="distill-lint-cli-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, self.SCRIPT] + list(args),
            capture_output=True, text=True)

    def test_exit_zero_on_valid_nodes(self):
        # 상호 링크하는 유니크 slug 신규 노드 2개 → corpus(+대상) 기준 위반 0 → exit 0
        pa = os.path.join(self.tmp, "distill-lint-selftest-a.md")
        pb = os.path.join(self.tmp, "distill-lint-selftest-b.md")
        _write(pa, _node_md(body="[[distill-lint-selftest-b]] 참고."))
        _write(pb, _node_md(body="[[distill-lint-selftest-a]] 참고."))
        r = self._run(pa, pb)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_exit_one_on_violation(self):
        p = os.path.join(self.tmp, "distill-lint-selftest-bad.md")
        _write(p, _node_md(ntype="bug-pattern", body="링크 없음."))
        r = self._run(p)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("type", r.stdout)


# ---------------------------------------------------------------------------
# 위반 2b. title — 빈 값/누락 (OKF 표준 필드)
# ---------------------------------------------------------------------------
class TestTitleRequired(LintFixtureTestCase):
    def test_missing_title_fails(self):
        p = os.path.join(self.wiki, "no-title.md")
        _write(p, _node_md(omit=("title",)))
        violations = self._lint(p)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("title", violations[0][1])

    def test_node_with_title_passes(self):
        p = os.path.join(self.wiki, "with-title.md")
        _write(p, _node_md())
        self.assertEqual(self._lint(p), [])


if __name__ == "__main__":
    unittest.main()
