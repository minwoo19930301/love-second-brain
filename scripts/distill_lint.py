#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
distill 산출물 strict lint.

app/brain.py의 parse_frontmatter·NODE_TYPES·링크 추출(_extract_links)을 그대로 재사용한다
(파싱 SoT 단일 — 파서를 여기서 재구현하지 않음). load_wiki_nodes()는 관대하게 보정하지만
(빈 type→claim 등), 이 lint는 strict — 위반은 곧 실패다.

검사 항목:
- type이 NODE_TYPES 6종 밖 (빈 값/누락 포함)
- tldr 빈 값/누락
- tags가 비리스트 또는 빈 리스트
- sources 누락/빈 리스트/항목이 dict(flow map) 아님 (distill 강화 규칙)
- sources의 url/path 실존 검사: raw/·wiki/ 시작은 repo 루트 기준, ./·../ 시작은 노드 위치 기준
  (http(s) 외부 URL·repo 표기 제외)
- dangling 링크 — 타깃 slug가 wiki corpus(+이번 lint 대상 중 실존 파일)에 없음
- 중복 slug — 같은 slug의 다른 파일이 wiki 또는 같은 lint 배치에 이미 존재
  (decision 근거: schema.md '관계 표기 권장'이라 supports 형식은 비강제 —
   근거 링크 자체는 아래 본문 링크 ≥1 검사가 보장)
- 본문 링크 0개면 실패 (distill 강화 규칙 — 연결 ≥1 의무)
- verified — 선택 필드(빈값/누락은 중립). 값이 있으면 schema.md 검증 등급 4종 enum 준수
- verified=domain-expert-verified인데 verified_by(확인한 사람) 누락 — 책임 추적

참고: "tldr 한/영 병기"·"어느 verified 등급이 맞는지"는 자동판정 불가 — lint 비검사,
PR 리뷰에서 확인 (SKILL.md 명시). lint는 verified 값이 유효한 enum인지만 본다.

사용법:
    python3 scripts/distill_lint.py [노드경로 ...]
인자가 없으면 wiki/ 전체를 검사. 위반을 "경로: 사유"로 출력하고,
위반 0이면 exit 0, 있으면 exit 1.
"""
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "app"))
import brain  # noqa: E402


def _wiki_files():
    """wiki/**/*.md 절대경로 리스트 (corpus)."""
    out = []
    if not os.path.isdir(brain.WIKI_DIR):
        return out
    for root, _, files in os.walk(brain.WIKI_DIR):
        for fn in sorted(files):
            if fn.endswith(".md"):
                out.append(os.path.join(root, fn))
    return out


def _slug(path):
    """파일명 → slug (load_wiki_nodes와 동일: 확장자 제거 + lower)."""
    name = os.path.basename(path)
    if name.endswith(".md"):
        name = name[:-3]
    return name.lower()


def _rel(path):
    """출력용 경로 — BRAIN_DIR 기준 상대경로 (밖이면 원래 경로)."""
    rel = os.path.relpath(path, brain.BRAIN_DIR)
    return path if rel.startswith("..") else rel


# verified 검증 등급 (schema.md "검증 등급" 표). 선택 필드 — 있으면 enum 준수, 없으면 통과.
# 형식 검사(유효 enum인지)만 한다 — 어느 등급이 옳은지는 자동판정 불가, PR 리뷰 몫.
VERIFIED_LEVELS = (
    "unverified-capture",      # 초기 캡처, 명시적 미검증 (→ ⚠). 템플릿 기본값은 빈값(중립)
    "code-verified",           # 코드/원본 대조로 검증된 기계적 사실 (반증가능)
    "domain-expert-verified",  # 도메인 전문가가 비즈니스 의미 확인 (verified_by 의무)
    "provisional",             # 해석성 주장(버그·의도 추정), 전문가 확인 대기
)


def _strip_inline_comment(v):
    """스칼라 값의 inline '#' 주석을 떼어 정규화한다 (verified/verified_by 전용).

    brain.parse_frontmatter는 비-YAML 최소 파서라 `key: val   # 주석`의 주석을
    값에 그대로 남긴다. verified/verified_by 같은 enum·식별자 값엔 '#'가 들어갈 일이
    없으므로, 검사 직전 첫 '#' 이후를 잘라 "주석만 남은 값"이 통과하는 우회를 막는다.
    (tldr 등 본문성 필드엔 '#'가 정상 등장할 수 있어 적용하지 않는다.)
    """
    if not isinstance(v, str):
        return v
    return v.split("#", 1)[0].strip()


def lint_files(paths):
    """노드 파일들을 strict 검사. [(출력경로, 사유)] 반환 — 위반 0개면 빈 리스트."""
    corpus = _wiki_files()
    # 미존재 입력 경로는 "경로 없음" 위반으로만 보고 — slug 합산에서 제외해
    # dangling 억제(미존재 ghost.md를 같이 넘겨 [[ghost]]를 통과시키는 우회)를 막는다.
    existing = [p for p in paths if os.path.isfile(p)]
    # dangling 판정 corpus: 기존 wiki slug + 이번 lint 대상 중 실존 slug (신규 파일 상호 링크 허용)
    known_slugs = {_slug(p) for p in corpus}
    known_slugs |= {_slug(p) for p in existing}
    # 중복 slug 판정: corpus + 같은 배치 실존 파일 (realpath 키로 corpus/배치 중복 합산 방지)
    slug_files = {}
    for p in corpus + existing:
        slug_files.setdefault(_slug(p), {})[os.path.realpath(p)] = p

    violations = []
    for path in paths:
        rel = _rel(path)
        if not os.path.isfile(path):
            violations.append((rel, "파일이 존재하지 않음"))
            continue
        meta, body = brain.parse_frontmatter(brain._read(path))

        # 1. type — NODE_TYPES 6종 밖 (빈 값/누락 포함)
        ntype = meta.get("type")
        if not isinstance(ntype, str) or ntype not in brain.NODE_TYPES:
            violations.append((rel, "type이 %s 중 하나가 아님 (현재: %r)"
                               % ("/".join(brain.NODE_TYPES), ntype)))

        # 2. tldr — 빈 값/누락
        tldr = meta.get("tldr")
        if not isinstance(tldr, str) or not tldr.strip():
            violations.append((rel, "tldr 누락 또는 빈 값"))

        # 2b. title — 빈 값/누락 (OKF 표준 필드)
        title = meta.get("title")
        if not isinstance(title, str) or not title.strip():
            violations.append((rel, "title 누락 또는 빈 값 (OKF 표준 필드)"))

        # 3. tags — 비리스트 또는 빈 리스트
        tags = meta.get("tags")
        if not isinstance(tags, list) or not tags:
            violations.append((rel, "tags가 리스트가 아니거나 빈 리스트"))

        # 4. sources — 누락/빈 리스트/항목이 dict 아님 (distill 강화 규칙)
        sources = meta.get("sources")
        if not isinstance(sources, list) or not sources:
            violations.append((rel, "sources 누락 또는 빈 리스트 (distill은 출처 의무)"))
        elif not all(isinstance(s, dict) for s in sources):
            violations.append((rel, "sources 항목이 dict(flow map) 형식이 아님"))
        else:
            # 4b. 로컬 경로 실존 검사 (http(s) 외부 URL·repo 표기는 대상 아님)
            #     - raw/·wiki/ 시작: repo 루트 기준
            #     - ./·../ 시작: 노드 파일 위치 기준 (corpus 관례 — ../../raw/... 스타일)
            for s in sources:
                for key in ("url", "path"):
                    v = s.get(key)
                    if not isinstance(v, str):
                        continue
                    if v.startswith("raw/") or v.startswith("wiki/"):
                        resolved = os.path.join(brain.BRAIN_DIR, v)
                    elif v.startswith("./") or v.startswith("../"):
                        resolved = os.path.normpath(os.path.join(os.path.dirname(path), v))
                    else:
                        continue
                    if not os.path.isfile(resolved):
                        violations.append((rel, "sources %s 경로가 실존하지 않음: %s" % (key, v)))

        # 5. dangling 링크 (마크다운 링크 + 레거시 [[ ]] 모두 brain._extract_links가 추출)
        links = brain._extract_links(body)
        seen_dangling = set()
        for target, _relname in links:
            if target not in known_slugs and target not in seen_dangling:
                seen_dangling.add(target)
                violations.append((rel, "dangling 링크 — wiki에 없는 slug: %s" % target))

        # 6. 중복 slug — 같은 slug의 다른 파일이 wiki 또는 같은 lint 배치에 존재
        slug = _slug(path)
        real = os.path.realpath(path)
        for other_real, other in sorted(slug_files.get(slug, {}).items()):
            if other_real != real:
                violations.append((rel, "중복 slug — %s 이(가) 이미 존재" % _rel(other)))

        # (decision 근거: schema.md는 '관계 표기 권장'이므로 supports '형식'은 비강제.
        #  근거 링크 자체는 아래 검사 8(본문 링크 ≥1)이 보장한다.)

        # 8. 본문 링크 ≥ 1 — distill 강화 규칙
        if not links:
            violations.append((rel, "본문에 링크가 0개 (마크다운 링크로 기존/배치 노드 연결 ≥1 의무)"))

        # 9. verified — 선택 필드. 값이 있으면 enum 준수, 없으면 통과(optional).
        #    빈값(미부여)은 중립 — 누락(None)/빈 값(`verified:`→[])/주석만 남은 값("")
        #    모두 falsy라 통과시킨다. 템플릿 기본값을 비워도(중립 시작) lint가 안 깨지게.
        #    lint 통과 ≠ 사실 — 등급을 항상 달게 하는 건 lint가 아니라 distill 절차(SKILL.md)의 몫.
        verified = _strip_inline_comment(meta.get("verified"))
        if verified and verified not in VERIFIED_LEVELS:
            violations.append((rel, "verified가 %s 중 하나가 아님 (현재: %r)"
                               % ("/".join(VERIFIED_LEVELS), verified)))

        # 10. domain-expert-verified면 verified_by(확인한 사람) 의무 — 책임 추적
        #     (이름 없는 expert-verified는 검증불가한 self-promotion이라 불인정)
        #     verified_by에 주석만 남은 값은 _strip_inline_comment가 ""로 만들어 거른다.
        if verified == "domain-expert-verified":
            vby = _strip_inline_comment(meta.get("verified_by"))
            if not vby:
                violations.append((rel, "verified=domain-expert-verified엔 verified_by(확인한 사람) 의무 "
                                        "(주석만 있는 값은 불인정)"))

    return violations


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    paths = args if args else _wiki_files()
    violations = lint_files(paths)
    for rel, reason in violations:
        print("%s: %s" % (rel, reason))
    if violations:
        print("FAIL: 위반 %d건 (검사 %d개 파일)" % (len(violations), len(paths)))
        return 1
    print("OK: 위반 0건 (검사 %d개 파일)" % len(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
