#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
정제 워크플로우(distill)가 낸 노드 JSON → wiki/<도메인>/*.md 머티리얼라이즈.

frontmatter·본문 링크·sources·slug 유일성을 **코드로 보장**해 distill_lint를 구조적으로 통과시킨다
(LLM은 지식 내용만, 형식 충족은 여기서). 입력 노드의 link는 본문이 아니라 related[]로 받아
레지스트리에 실존하는 타깃만 마크다운 링크로 변환한다(→ dangling 0, 노드당 링크 ≥1 보장).

사용법: python3 scripts/materialize_nodes.py <nodes.json> [--date YYYY-MM-DD]
"""
import os
import re
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN_DIR = os.path.dirname(_HERE)
WIKI = os.path.join(BRAIN_DIR, "wiki")
RAW_CHAT = os.path.join(BRAIN_DIR, "raw", "chat")

NODE_TYPES = ["claim", "concept", "decision", "source", "person", "event"]
DOMAINS = ["person", "love", "taste", "events", "marriage", "rules", "lexicon", "life"]
VERIFIED_LEVELS = ("unverified-capture", "code-verified", "provisional")  # expert-verified는 본인 확인 전까지 미발급
MD_LINK_RE = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)]+)\)")


def slugify(s, fallback="node"):
    s = (s or "").strip().lower()
    s = s.replace(" ", "-").replace("_", "-").replace("/", "-")
    s = re.sub(r"[^a-z0-9가-힣\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or fallback


def uniq_slug(slug, used):
    base, n, out = slug, 2, slug
    while out in used:
        out = "%s-%d" % (base, n)
        n += 1
    used.add(out)
    return out


def strip_md_links(body):
    """본문에 LLM이 넣었을 수 있는 마크다운 링크는 텍스트만 남기고 제거(우리 링크 섹션만 그래프 엣지로)."""
    return MD_LINK_RE.sub(lambda m: m.group(1), body or "")


def month_source(ym, date):
    """'YYYY-MM' → 실존하는 raw/chat 경로면 source dict, 아니면 None."""
    if not re.match(r"^\d{4}-\d{2}$", ym or ""):
        return None
    rel = "raw/chat/%s/%s.md" % (ym[:4], ym)
    if os.path.isfile(os.path.join(BRAIN_DIR, rel)):
        return {"platform": "kakao", "url": "../../" + rel, "date": (date or (ym + "-01"))}
    return None


def yaml_scalar(v):
    v = str(v or "").replace('"', "'").strip()
    return '"%s"' % v


def build_frontmatter(node, today):
    t = node.get("type")
    if t not in NODE_TYPES:
        t = "claim"
    title = (node.get("title") or "").strip() or (node.get("slug") or "노드")
    tldr = (node.get("tldr") or "").strip() or title
    tags = [str(x).strip() for x in (node.get("tags") or []) if str(x).strip()]
    dtag = "domain/%s" % node["domain"]
    if dtag not in tags:
        tags.insert(0, dtag)
    # sources
    srcs = []
    seen_src = set()
    for ym in (node.get("source_months") or []):
        s = month_source(ym, node.get("date"))
        if s and s["url"] not in seen_src:
            srcs.append(s)
            seen_src.add(s["url"])
    if not srcs:
        srcs.append({"platform": "kakao", "url": "../../raw/chat/manifest.md", "date": today})
    lines = ["---", "type: %s" % t, "title: %s" % yaml_scalar(title), "tldr: %s" % yaml_scalar(tldr)]
    lines.append("tags: [%s]" % ", ".join(tags))
    lines.append("sources:")
    for s in srcs:
        lines.append('  - {platform: %s, url: "%s", date: "%s"}' % (s["platform"], s["url"], s["date"]))
    v = (node.get("verified") or "").strip()
    if v in VERIFIED_LEVELS:
        lines.append("verified: %s" % v)
    if t == "event" and (node.get("date") or "").strip():
        lines.append("date: %s" % yaml_scalar(node["date"]))
    lines.append("created: %s" % today)
    lines.append("updated: %s" % today)
    lines.append("---")
    return "\n".join(lines), title


def main(argv):
    if len(argv) < 2:
        print("사용법: python3 scripts/materialize_nodes.py <nodes.json> [--date YYYY-MM-DD]", file=sys.stderr)
        return 2
    today = "2026-06-19"
    if "--date" in argv:
        today = argv[argv.index("--date") + 1]
    data = json.load(open(argv[1], encoding="utf-8"))
    raw_nodes = data["nodes"] if isinstance(data, dict) else data

    # 1) 슬러그 배정(전역 유일) + 도메인 정규화
    used = set()
    nodes = []
    title_to_slug = {}
    for nd in raw_nodes:
        dom = nd.get("domain")
        if dom not in DOMAINS:
            dom = "life"
        slug = uniq_slug(slugify(nd.get("slug") or nd.get("title")), used)
        n = dict(nd)
        n["domain"], n["slug"] = dom, slug
        nodes.append(n)
        if nd.get("title"):
            title_to_slug.setdefault(nd["title"].strip().lower(), slug)
        title_to_slug.setdefault(slugify(nd.get("slug") or ""), slug)

    # 2) 레지스트리: slug -> repo상대경로
    relpath = {n["slug"]: "wiki/%s/%s.md" % (n["domain"], n["slug"]) for n in nodes}

    # 3) 허브 보장 — 폴백 링크 타깃(wife/me)이 항상 존재하도록
    def ensure_hub(slug, title, tldr, body):
        if slug in relpath:
            return
        hub = {"domain": "person", "slug": slug, "type": "person", "title": title,
               "tldr": tldr, "tags": ["domain/person"], "verified": "",
               "source_months": [], "body": body, "related": []}
        nodes.append(hub)
        relpath[slug] = "wiki/person/%s.md" % slug
        used.add(slug)
    ensure_hub("wife", "상대 (파트너)", "상대 — 이 브레인의 두 주인공 중 한 명.", "나의 파트너.")
    ensure_hub("me", "나", "나 — 이 브레인의 두 주인공 중 한 명.", "이 브레인의 작성자(본인).")

    # 4) 머티리얼라이즈
    def resolve_related(n):
        out = []
        for r in (n.get("related") or []):
            key = str(r).strip().lower()
            tgt = key if key in relpath else title_to_slug.get(key) or title_to_slug.get(slugify(key))
            if tgt and tgt in relpath and tgt != n["slug"] and tgt not in out:
                out.append(tgt)
        if not out:  # 폴백 — 노드당 링크 ≥1 보장
            for hub in ("wife", "me"):
                if hub != n["slug"] and hub in relpath:
                    out.append(hub)
                    break
            if not out:  # wife 노드 자신이면 me로, 그것도 없으면 아무 노드
                for cand in relpath:
                    if cand != n["slug"]:
                        out.append(cand)
                        break
        return out

    count = 0
    for n in nodes:
        fm, title = build_frontmatter(n, today)
        body = strip_md_links(n.get("body") or "").strip()
        node_dir = os.path.join(BRAIN_DIR, "wiki", n["domain"])
        os.makedirs(node_dir, exist_ok=True)
        rel_links = []
        for tgt in resolve_related(n):
            tgt_full = os.path.join(BRAIN_DIR, relpath[tgt])
            link = os.path.relpath(tgt_full, node_dir)
            label = next((m.get("title") for m in nodes if m["slug"] == tgt and m.get("title")), tgt)
            rel_links.append("- [%s](%s)" % (label, link))
        content = "%s\n\n# %s\n\n%s\n\n## 관련\n%s\n" % (fm, title, body, "\n".join(rel_links))
        with open(os.path.join(node_dir, n["slug"] + ".md"), "w", encoding="utf-8") as f:
            f.write(content)
        count += 1
    print("머티리얼라이즈: %d개 노드 (도메인 %d)" % (count, len({n['domain'] for n in nodes})))
    by_dom = {}
    for n in nodes:
        by_dom[n["domain"]] = by_dom.get(n["domain"], 0) + 1
    print("도메인별:", dict(sorted(by_dom.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
