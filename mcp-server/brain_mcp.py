#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Love Second Brain MCP 서버.

raw/(불변 원본: 카카오톡 대화) + wiki/(정제 노드) 마크다운 브레인를 Claude 앱에 도구로 노출한다.
이 repo 폴더를 Claude 앱으로 열기만 하면 (repo 루트의 .mcp.json 으로)
이 서버가 자동 연결되고, Claude가 search_brain → read_doc 으로 근거를 찾아 답한다.
별도 CLI 설치·로그인·API key 불필요 — Claude 앱의 기존 구독 인증을 그대로 사용한다.

프로토콜: MCP stdio (JSON-RPC 2.0, 줄 단위 JSON). 표준라이브러리만 사용.
직접 실행해 수동 테스트도 가능:  echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 mcp-server/brain_mcp.py
"""
import os
import sys
import json

# 공유 데이터 레이어(app/brain.py) import — repo 구조 기준 절대경로로 해석.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "app"))
import brain  # noqa: E402

SERVER_NAME = "love-brain"
SERVER_VERSION = "1.0.0"
DEFAULT_PROTOCOL = "2024-11-05"


def log(*a):
    print("[brain-mcp]", *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# 도구 정의
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "search_brain",
        "description": (
            "Love Second Brain(raw 카톡 원본 + wiki 정제 노드)을 키워드로 검색한다. "
            "질문에 답하기 전에 먼저 이 도구로 관련 노드/원본을 찾을 것. "
            "결과의 경로(path)를 read_doc 으로 열어 본문을 확인하고, 답변에 path를 인용한다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색어(한/영). 예: '기념일', '아내 음식 취향', '둘만의 별명'"},
                "limit": {"type": "integer", "description": "각 영역(wiki/raw) 최대 결과 수", "default": 12},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_doc",
        "description": "브레인의 특정 파일 전문을 읽는다. raw/ 또는 wiki/ 하위 상대경로만 허용.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "상대경로. 예: 'wiki/person/wife.md' 또는 'raw/chat/2021/2021-03.md'"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_nodes",
        "description": "wiki 정제 노드 목록(slug·type·tldr·tags·path). type 또는 tag로 필터 가능.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "노드 타입 필터(claim/concept/decision/source/person/event)", "enum": brain.NODE_TYPES},
                "tag": {"type": "string", "description": "태그 부분일치 필터. 예: 'domain/love', 'topic/anniversary'"},
            },
        },
    },
    {
        "name": "get_node",
        "description": "wiki 노드 하나의 전체 정보(type·verified 등급·tldr·tags·sources·본문 + 연결된 마크다운 링크). 그래프 탐색에 사용. verified가 ⚠(provisional/미검증)면 단정 인용 금지.",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "노드 slug(파일명, .md 제외). 예: 'wife'"}},
            "required": ["slug"],
        },
    },
    {
        "name": "brain_overview",
        "description": "브레인 전체 개요 — raw/wiki 카운트, 타입/도메인 분포, 최근 활동(log), 노드 slug 목록. 처음 방향 잡을 때 호출.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ---------------------------------------------------------------------------
# 도구 구현 → 텍스트 반환
# ---------------------------------------------------------------------------
RAW_EXCERPT_TOP = 5   # raw 결과 중 본문 발췌를 포함할 상위 개수 (6위~는 제목+path만)


def tool_search_brain(args):
    query = (args.get("query") or "").strip()
    if not query:
        return "query가 비어 있습니다."
    limit = int(args.get("limit") or 12)
    wiki_hits, raw_hits = brain.search(query, k_wiki=limit, k_raw=limit)
    if not wiki_hits and not raw_hits:
        return f"'{query}'에 대한 결과가 브레인에 없습니다. 더 일반적인 키워드로 다시 시도해 보세요."
    kws = brain.expand_kws(brain.tokenize(query))   # 발췌 위치 탐색에도 alias 확장 적용
    out = [f"# 검색: \"{query}\""]
    if wiki_hits:
        out.append(f"\n## wiki 정제 노드 ({len(wiki_hits)})")
        for i, (score, n) in enumerate(wiki_hits, 1):
            vt = brain.verified_tag(n)
            head = f"{n['type']}·{vt}" if vt else n['type']
            out.append(f"{i}. [{head}] **{n['slug']}** — {n['tldr']}\n   path: `{n['path']}`")
    if raw_hits:
        out.append(f"\n## raw 원본 발췌 ({len(raw_hits)})")
        for i, (score, d, text) in enumerate(raw_hits, 1):
            if i <= RAW_EXCERPT_TOP:
                out.append(f"{i}. **{d['title']}**\n   path: `{d['path']}`\n   > {brain.excerpt_around(text, kws, 400)}")
            else:   # 꼬리는 발췌 생략 — 필요 시 read_doc로 열도록
                out.append(f"{i}. **{d['title']}**\n   path: `{d['path']}`")
    out.append("\n→ 전문이 필요하면 read_doc(path) 로 열고, 답변에 path를 인용하세요.")
    if any("⚠" in brain.verified_tag(n) for _, n in wiki_hits):
        out.append("⚠ 표시(provisional·미검증) 노드는 검증된 사실로 단정하지 말고 '미확인'임을 밝혀 인용하세요.")
    return "\n".join(out)


def tool_read_doc(args):
    path = (args.get("path") or "").strip()
    full = brain.safe_join(path)
    if not full:
        return f"파일을 찾을 수 없거나 허용되지 않은 경로입니다: '{path}' (raw/ 또는 wiki/ 하위만 가능)"
    content = brain._read(full)
    return f"# {path}\n\n{content}"


def tool_list_nodes(args):
    nodes = brain.load_wiki_nodes()
    tfilter = args.get("type")
    tagf = (args.get("tag") or "").lower()
    if tfilter:
        nodes = [n for n in nodes if n["type"] == tfilter]
    if tagf:
        nodes = [n for n in nodes if any(tagf in t.lower() for t in n["tags"])]
    if not nodes:
        return "조건에 맞는 노드가 없습니다."
    out = [f"# wiki 노드 ({len(nodes)})"]
    for n in nodes:
        tags = " ".join(f"#{t}" for t in n["tags"])
        vt = brain.verified_tag(n)
        head = f"{n['type']}·{vt}" if vt else n['type']
        out.append(f"- [{head}] **{n['slug']}** — {n['tldr']}  {tags}\n  `{n['path']}`")
    return "\n".join(out)


def tool_get_node(args):
    slug = (args.get("slug") or "").strip().lower().replace(".md", "")
    n = next((x for x in brain.load_wiki_nodes() if x["slug"] == slug), None)
    if not n:
        return f"'{slug}' 노드를 찾을 수 없습니다. list_nodes 로 목록을 확인하세요."
    src = "\n".join(f"  - [{s.get('platform','')}] {s.get('date','')} {s.get('url','')}" for s in n["sources"]) or "  (없음)"
    links = "\n".join(f"  - {t} ({rel})" for t, rel in n["links"]) or "  (없음)"
    return (
        f"# {n['slug']}  ({n['type']})\n"
        f"verified: {brain.verified_label(n)}\n"
        f"tldr: {n['tldr']}\n"
        f"tags: {', '.join(n['tags'])}\n"
        f"path: `{n['path']}`  (updated {n['updated'] or '—'})\n\n"
        f"## 본문\n{n['body']}\n\n"
        f"## sources\n{src}\n\n"
        f"## 연결된 노드 (links)\n{links}"
    )


def tool_brain_overview(args):
    wiki = brain.load_wiki_nodes()
    raw = brain.list_raw_docs()
    graph = brain.build_graph(wiki)
    by_type, by_domain, by_verified = {}, {}, {}
    for n in wiki:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
        by_domain[n["domain"]] = by_domain.get(n["domain"], 0) + 1
        vkey = n["verified"] or "(미표기)"
        by_verified[vkey] = by_verified.get(vkey, 0) + 1
    real_slugs = {nn["slug"] for nn in graph["nodes"] if nn["type"] != "stub"}
    edges = len([l for l in graph["links"] if l["target"] in real_slugs])
    raw_dom = {}
    for d in raw:
        raw_dom[d["domain"]] = raw_dom.get(d["domain"], 0) + 1
    log_lines = "\n".join(f"  - [{e['date']}] {e['action']} | {e['title']}" for e in brain.parse_log()[:6]) or "  (없음)"
    return (
        f"# Love Second Brain 개요\n"
        f"- raw 원본: {len(raw)}개  {dict(sorted(raw_dom.items()))}\n"
        f"- wiki 노드: {len(wiki)}개  타입={by_type}  도메인={by_domain}\n"
        f"- 검증 등급: {by_verified}  (⚠는 provisional·unverified-capture·확인자 없는 expert 등 **명시적** 미검증만; '(미표기)'는 등급 미부여=중립)\n"
        f"- 연결 엣지: {edges}개\n\n"
        f"## 노드 목록\n" + "\n".join(f"  - [{n['type']}] {n['slug']} — {n['tldr']}" for n in wiki) +
        f"\n\n## 최근 활동 (log.md)\n{log_lines}\n\n"
        f"→ 세부는 search_brain(query) / get_node(slug) / read_doc(path)."
    )


HANDLERS = {
    "search_brain": tool_search_brain,
    "read_doc": tool_read_doc,
    "list_nodes": tool_list_nodes,
    "get_node": tool_get_node,
    "brain_overview": tool_brain_overview,
}


# ---------------------------------------------------------------------------
# JSON-RPC / MCP 디스패치
# ---------------------------------------------------------------------------
def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def result(req_id, res):
    send({"jsonrpc": "2.0", "id": req_id, "result": res})


def error(req_id, code, message):
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle(req):
    if not isinstance(req, dict):
        return
    method = req.get("method")
    req_id = req.get("id")
    is_notification = "id" not in req

    if method == "initialize":
        params = req.get("params") or {}
        proto = params.get("protocolVersion") or DEFAULT_PROTOCOL
        return result(req_id, {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    if method == "ping":
        return result(req_id, {})

    if method == "tools/list":
        return result(req_id, {"tools": TOOLS})

    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if not fn:
            return result(req_id, {"content": [{"type": "text", "text": f"알 수 없는 도구: {name}"}], "isError": True})
        try:
            text = fn(args)
            return result(req_id, {"content": [{"type": "text", "text": text}]})
        except Exception as e:  # 도구 오류는 isError로 전달(서버는 죽지 않음)
            log("tool error", name, repr(e))
            return result(req_id, {"content": [{"type": "text", "text": f"도구 실행 오류: {e}"}], "isError": True})

    if is_notification:
        return  # notifications/initialized 등 — 응답 없음

    error(req_id, -32601, f"Method not found: {method}")


def main():
    log(f"started — 브레인={brain.BRAIN_DIR} ({len(brain.load_wiki_nodes())} nodes, {len(brain.list_raw_docs())} raw)")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            error(None, -32700, "Parse error")
            continue
        try:
            if isinstance(msg, list):     # JSON-RPC 배치(드묾)
                for m in msg:
                    handle(m)
            else:
                handle(msg)
        except Exception as e:
            log("fatal-ish in handle:", repr(e))
    log("stdin closed — exiting")


if __name__ == "__main__":
    main()
