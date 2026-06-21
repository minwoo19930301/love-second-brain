#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wiki/**/*.md frontmatter에 title이 없으면 본문 첫 H1(`# ...`)을 title로 주입(일회성).

- title 탐지는 **frontmatter 블록만** 대상 (본문 코드펜스 안 `title:` 오탐 방지).
- H1 탐지는 **코드펜스 제외** 본문에서 (펜스 안 `# 주석` 오탐 방지).
- H1이 없으면 건드리지 않고 목록만 출력 → 사람이 직접 title을 단다.
- title 값은 큰따옴표로 감싸 colon/특수문자 안전. (brain.parse_frontmatter가 quote 해제)

사용법: python3 scripts/backfill_titles.py [--apply]   (기본 dry-run)
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI = os.path.join(REPO, "wiki")
FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def main():
    apply = "--apply" in sys.argv[1:]
    done, missing = 0, []
    for root, _, names in os.walk(WIKI):
        for fn in sorted(names):
            if not fn.endswith(".md") or fn.lower() == "index.md":
                continue
            p = os.path.join(root, fn)
            text = open(p, encoding="utf-8").read()
            m = FM_RE.match(text)
            if not m:
                missing.append(p)
                continue
            head, block, sep, body = m.groups()
            if re.search(r"^title:", block, re.MULTILINE):
                continue                                        # 이미 있음
            h1 = H1_RE.search(FENCE_RE.sub("", body))           # 펜스 제외 본문에서 첫 H1
            if not h1:
                missing.append(p)
                continue
            title = h1.group(1).strip().replace('"', "'")
            # type 라인 바로 뒤에 title 삽입 (없으면 블록 맨 앞). 함수 치환으로 backref 안전.
            block2, n = re.subn(r"^type:.*\n",
                                lambda mm: mm.group(0) + 'title: "%s"\n' % title,
                                block, count=1, flags=re.MULTILINE)
            if n == 0:
                block2 = 'title: "%s"\n' % title + block
            done += 1
            if apply:
                open(p, "w", encoding="utf-8").write(head + block2 + sep + body)
    print("%s: backfilled %d" % ("APPLIED" if apply else "DRY-RUN", done))
    print("NO H1 (write by hand): %d" % len(missing))
    for p in missing:
        print("  -", os.path.relpath(p, REPO))


if __name__ == "__main__":
    main()
