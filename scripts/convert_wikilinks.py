#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot: wiki/**/*.md 의 [[slug]] / [[slug|label]] → 상대경로 마크다운 링크.

OKF 정합: 그래프는 표준 마크다운 링크 [표시](상대경로.md)로 구성한다.
- raw/·log.md 는 비대상(불변 원본·역사 보존 — 이 스크립트는 wiki/ 만 순회).
- 코드펜스(``` ... ```) 안의 [[ ]]는 보존(ASCII 다이어그램·예시 — 렌더링상 링크 아님).
- 미해결 slug(=dangling)는 보존([[ ]] 유지) — distill_lint가 잡게.
- basename이 전 코퍼스 유일하므로 slug→파일 매핑은 결정적, 상대경로도 결정적(POSIX).

사용법: python3 scripts/convert_wikilinks.py [--apply]   (기본 dry-run)
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI = os.path.join(REPO, "wiki")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def build_slug_map():
    """slug(=파일명 소문자, .md 제거) → 절대경로. index.md 제외."""
    m = {}
    for root, _, files in os.walk(WIKI):
        for fn in files:
            if fn.endswith(".md") and fn.lower() != "index.md":
                m[fn[:-3].lower()] = os.path.join(root, fn)
    return m


def convert_file(path, slug_map):
    text = open(path, encoding="utf-8").read()
    fences = [(fm.start(), fm.end()) for fm in FENCE_RE.finditer(text)]

    def in_fence(pos):
        return any(s <= pos < e for s, e in fences)

    src_dir = os.path.dirname(path)
    n = [0]

    def repl(m):
        if in_fence(m.start()):
            return m.group(0)                       # 코드펜스 보존
        inner = m.group(1)
        slug = inner.split("|")[0].split("#")[0].strip().lower()
        label = inner.split("|")[1].strip() if "|" in inner else inner.split("#")[0].strip()
        target = slug_map.get(slug)
        if not target:
            return m.group(0)                       # 미해결 → 보존(lint가 잡음)
        rel = os.path.relpath(target, src_dir).replace(os.sep, "/")
        n[0] += 1
        return "[%s](%s)" % (label, rel)

    return WIKILINK_RE.sub(repl, text), n[0]


def main():
    apply = "--apply" in sys.argv[1:]
    slug_map = build_slug_map()
    total, files = 0, 0
    for root, _, names in os.walk(WIKI):
        for fn in sorted(names):
            if not fn.endswith(".md") or fn.lower() == "index.md":
                continue
            p = os.path.join(root, fn)
            new, c = convert_file(p, slug_map)
            if c:
                files += 1
                total += c
                if apply:
                    open(p, "w", encoding="utf-8").write(new)
    print("%s: %d links in %d files" % ("APPLIED" if apply else "DRY-RUN", total, files))


if __name__ == "__main__":
    main()
