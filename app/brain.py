# -*- coding: utf-8 -*-
"""
Love Second Brain — 공유 데이터 레이어.

raw/(불변 원본: 카톡 대화) + wiki/(정제 노드) 마크다운 브레인를 파싱·검색하는 순수 표준라이브러리 모듈.
대시보드 서버(app/server.py)와 MCP 서버(mcp-server/brain_mcp.py)가 함께 import 한다.
의존성 없음.
"""
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))   # .../app
BRAIN_DIR = os.path.dirname(_HERE)                    # repo 루트
RAW_DIR = os.path.join(BRAIN_DIR, "raw")
WIKI_DIR = os.path.join(BRAIN_DIR, "wiki")
LOG_PATH = os.path.join(BRAIN_DIR, "log.md")

NODE_TYPES = ["claim", "concept", "decision", "source", "person", "event"]


def _read(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Frontmatter 파서 (PyYAML 없이 — tags 인라인리스트 / sources 플로우맵 처리)
# ---------------------------------------------------------------------------
def _strip_quotes(s):
    s = s.strip()
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        return s[1:-1]
    return s


def _split_top_level(s, sep=","):
    """따옴표/중괄호를 존중하며 top-level 구분자로 분리."""
    out, buf, depth, quote = [], [], 0, None
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "{[":
            depth += 1
            buf.append(ch)
        elif ch in "}]":
            depth -= 1
            buf.append(ch)
        elif ch == sep and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return [x.strip() for x in out if x.strip()]


def _parse_flow_map(s):
    """{platform: kakao, url: "...", date: "2021-03-14"} → dict (YAML flow map)."""
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    d = {}
    for pair in _split_top_level(s, ","):
        if ":" in pair:
            k, v = pair.split(":", 1)
            d[k.strip()] = _strip_quotes(v)
    return d


def _coerce_scalar(v):
    vc = _strip_quotes(v)
    low = vc.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    return vc


def parse_frontmatter(content):
    """('---' 블록, 본문) → (meta dict, body str). frontmatter 없으면 ({}, content)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not m:
        return {}, content
    block, body = m.group(1), m.group(2)
    meta = {}
    cur_key = None
    for raw_line in block.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- ") and cur_key is not None:   # 블록 리스트 항목
            item = line.lstrip()[2:].strip()
            if isinstance(meta.get(cur_key), list):
                meta[cur_key].append(_parse_flow_map(item) if item.startswith("{") else _strip_quotes(item))
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        cur_key = key
        if val == "" or val == "[]":
            meta[key] = []
        elif val.startswith("[") and val.endswith("]"):            # 인라인 리스트
            inner = val[1:-1].strip()
            items = _split_top_level(inner, ",") if inner else []
            meta[key] = [_parse_flow_map(x) if x.startswith("{") else _strip_quotes(x) for x in items]
        else:
            meta[key] = _coerce_scalar(val)
    return meta, body.strip()


# ---------------------------------------------------------------------------
# 노드 / 그래프 / 원본 로딩
# ---------------------------------------------------------------------------
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
# OKF: 표준 마크다운 링크 [text](target). 이미지 임베드 ![alt](src)는 negative lookbehind로 제외.
MD_LINK_RE = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)]+)\)")
REL_KEYWORDS = ["supports", "contradicts", "extends", "similar"]


def _domain_from_relpath(rel):
    parts = rel.replace("\\", "/").split("/")
    if len(parts) >= 3:        # raw/<domain>/...  ·  wiki/<domain>/...
        return parts[1]
    return "general"           # raw/ · wiki/ 바로 아래 파일


def _md_link_slug(target):
    """OKF 마크다운 링크 타깃 → wiki 노드 slug. 엣지가 아니면 None.
    제외: 앵커 전용(#...), 외부 URL(://), 비-.md 프로즈, raw/ 대상(노드 없음)."""
    t = (target or "").strip()
    if not t or t.startswith("#") or t.startswith("//") or "://" in t:
        return None                          # 앵커 전용 / proto-relative(//) / 외부 URL
    t = t.split("#", 1)[0].strip()           # 앵커 제거
    if not t.endswith(".md"):
        return None
    norm = t.replace("\\", "/")
    if norm.startswith("raw/") or "/raw/" in norm:
        return None                          # 불변 raw/ 대상은 그래프 엣지 아님
    base = os.path.basename(norm)
    if base in ("index.md", "log.md"):       # OKF 예약 파일 — 노드 엣지 아님
        return None
    return base[:-3].strip().lower()


def _rel_on_line(body, pos):
    """링크가 놓인 줄에서 supports/contradicts/extends/similar 키워드를 찾아 rel 추론(기본 extends)."""
    line_start = body.rfind("\n", 0, pos) + 1
    line_end = body.find("\n", pos)
    line = body[line_start:(line_end if line_end != -1 else len(body))].lower()
    for kw in REL_KEYWORDS:
        if kw in line:
            return kw
    return "extends"


def _extract_links(body):
    """본문 링크 → [(target_slug, rel_type)].
    OKF 마크다운 링크 [text](상대경로.md) + 레거시 [[slug]]/[[slug|label]]/[[slug#anchor]] 둘 다 인식."""
    links = []
    for m in MD_LINK_RE.finditer(body):
        slug = _md_link_slug(m.group(2))
        if slug:
            links.append((slug, _rel_on_line(body, m.start())))
    for m in LINK_RE.finditer(body):
        target = m.group(1).split("|")[0].split("#")[0].strip().lower()
        if target:
            links.append((target, _rel_on_line(body, m.start())))
    return links


# 노드 증분 캐시 — 프로세스 메모리 전용. {절대경로: ((st_mtime_ns, st_size), node_dict)}
# 디스크 영속화 금지: 과거 memory-db.json이 stale로 폐기된 전례 — SoT는 항상 md 파일.
_NODE_CACHE = {}


def load_wiki_nodes():
    """wiki/**/*.md → 노드 리스트. mtime+size 스탬프 일치 시 캐시 재사용(증분 파싱)."""
    nodes = []
    if not os.path.isdir(WIKI_DIR):
        return nodes
    for root, _, files in os.walk(WIKI_DIR):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            full = os.path.join(root, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            stamp = (st.st_mtime_ns, st.st_size)
            cached = _NODE_CACHE.get(full)
            if cached is not None and cached[0] == stamp:
                nodes.append(cached[1])
                continue
            rel = os.path.relpath(full, BRAIN_DIR)
            meta, body = parse_frontmatter(_read(full))
            ntype = meta.get("type") or "claim"
            if not isinstance(ntype, str):
                ntype = "claim"
            tags = meta.get("tags") or []
            if not isinstance(tags, list):
                tags = [tags]
            sources = meta.get("sources") or []
            if not isinstance(sources, list):
                sources = []
            node = {
                "slug": fn[:-3].lower(),
                "title": str(meta.get("title") or "").strip(),   # OKF 표준 필드(선택)
                "type": ntype,
                "tldr": meta.get("tldr") or "",
                "tags": [t for t in tags if isinstance(t, str)],
                "sources": [s for s in sources if isinstance(s, dict)],
                "verified": str(meta.get("verified") or "").strip(),
                "verified_by": str(meta.get("verified_by") or "").strip(),
                "created": str(meta.get("created") or ""),
                "updated": str(meta.get("updated") or ""),
                "domain": _domain_from_relpath(rel),
                "path": rel,
                "body": body,
                "links": _extract_links(body),
            }
            _NODE_CACHE[full] = (stamp, node)   # 삭제 파일은 walk에 안 나와 자연 탈락
            nodes.append(node)
    return nodes


# verified 검증 등급 표시 — 미검증/해석성 노드를 답변·검색에서 눈에 띄게 (RAG 신뢰 가중치용).
# 등급 정의·강제(필수화)는 schema.md / scripts/distill_lint.py(VERIFIED_LEVELS) 소관. 여기선 표시만.
VERIFIED_TRUSTED = ("code-verified", "domain-expert-verified")


def _verified_warns(v, by):
    """그 등급이 ⚠(저신뢰)인가. verified는 optional이라 빈값(미부여)은 중립(⚠ 아님).
    명시적 저신뢰(provisional·unverified-capture·미정의값)와 확인자 없는 expert만 ⚠."""
    if not v:
        return False                          # 미부여 — 중립
    if v == "code-verified":
        return False
    if v == "domain-expert-verified":
        return not by                         # 확인자 없으면 ⚠
    return True                               # provisional·unverified-capture·미정의값


def verified_label(node):
    """노드 verified 등급을 사람이 읽는 한 줄 라벨로.
    verified는 optional — 빈값(미부여)은 중립으로 둔다(⚠ 없음). 명시적 저신뢰엔 ⚠('lint 통과 ≠ 사실')."""
    node = node or {}
    v = (node.get("verified") or "").strip()
    by = (node.get("verified_by") or "").strip()
    if not v:
        return "(verified 미표기)"             # optional — 중립
    if v == "code-verified":
        return "code-verified (코드 대조 사실)"
    if v == "domain-expert-verified":
        return ("domain-expert-verified (by %s)" % by if by
                else "domain-expert-verified ⚠ 확인자 미표기")
    if v == "provisional":
        return "provisional ⚠ 해석성 주장 — 도메인 전문가 미확인, 단정 인용 금지"
    if v == "unverified-capture":
        return "unverified-capture ⚠ 미검증 캡처"
    return "%s ⚠ 미정의 등급" % v               # 알 수 없는 값 — 원값 노출(타이포 surfacing)


def verified_tag(node):
    """검색/목록용 짧은 태그. 신뢰 등급은 그대로, 명시적 저신뢰엔 ⚠ 접미.
    빈값(미부여)은 ''(태그 생략 — optional 중립)이라 호출부가 '[type]'만 쓰게 한다.
    label과 동일 기준(_verified_warns)이라 알 수 없는 값도 원값+⚠로 일관 표시."""
    node = node or {}
    v = (node.get("verified") or "").strip()
    by = (node.get("verified_by") or "").strip()
    if not v:
        return ""
    return (v + "⚠") if _verified_warns(v, by) else v


def build_graph(nodes):
    """노드 + [[링크]] 엣지. 미해결 링크는 stub 노드로 추가."""
    slugs = {n["slug"] for n in nodes}
    g_nodes = [{
        "slug": n["slug"], "type": n["type"], "tldr": n["tldr"],
        "tags": n["tags"], "domain": n["domain"], "path": n["path"],
    } for n in nodes]
    links, seen, referenced = [], set(), set()
    for n in nodes:
        for target, rel in n["links"]:
            referenced.add(target)
            key = (n["slug"], target, rel)
            if key in seen:
                continue
            seen.add(key)
            links.append({"source": n["slug"], "target": target, "type": rel})
    for target in referenced:
        if target not in slugs:
            g_nodes.append({
                "slug": target, "type": "stub",
                "tldr": "(아직 작성되지 않은 노드 — 참조만 존재)",
                "tags": [], "domain": "stub", "path": "",
            })
    return {"nodes": g_nodes, "links": links}


# raw 원본 증분 캐시 — 프로세스 메모리 전용. {절대경로: ((st_mtime_ns, st_size), doc_dict, text, low_text)}
# _NODE_CACHE와 동일하게 디스크 영속화 금지 — SoT는 항상 md 파일. low_text는 검색 스코어링용.
_RAW_CACHE = {}


def list_raw_docs():
    """raw/**/*.md 메타데이터(경로·도메인·이름·제목). mtime+size 스탬프 일치 시 캐시 재사용."""
    docs = []
    if not os.path.isdir(RAW_DIR):
        return docs
    for root, _, files in os.walk(RAW_DIR):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            full = os.path.join(root, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            stamp = (st.st_mtime_ns, st.st_size)
            cached = _RAW_CACHE.get(full)
            if cached is not None and cached[0] == stamp:
                docs.append(cached[1])
                continue
            rel = os.path.relpath(full, BRAIN_DIR)
            text = _read(full)
            meta, body = parse_frontmatter(text)
            title = fn[:-3]
            mt = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
            if mt:
                title = mt.group(1).strip()
            doc = {
                "path": rel, "domain": _domain_from_relpath(rel), "name": fn,
                "title": title, "tldr": meta.get("tldr") or "", "size": len(body),
            }
            _RAW_CACHE[full] = (stamp, doc, text, text.lower())   # 삭제 파일은 walk에 안 나와 자연 탈락
            docs.append(doc)
    return docs


def parse_log():
    """log.md의 '## [YYYY-MM-DD] action | title' 라인 파싱 (최신순)."""
    entries = []
    if not os.path.exists(LOG_PATH):
        return entries
    for line in _read(LOG_PATH).split("\n"):
        m = re.match(r"^##\s*\[([0-9\-]+)\]\s*(\w+)\s*\|\s*(.+)$", line.strip())
        if m:
            entries.append({"date": m.group(1), "action": m.group(2), "title": m.group(3).strip()})
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


def safe_join(rel_path):
    """rel_path를 BRAIN_DIR 기준 절대경로로 해석하되 raw/·wiki/ 하위만 허용. 위반 시 None."""
    full = os.path.normpath(os.path.join(BRAIN_DIR, rel_path))
    if (full == RAW_DIR or full == WIKI_DIR
            or full.startswith(RAW_DIR + os.sep) or full.startswith(WIKI_DIR + os.sep)):
        if os.path.isfile(full):
            return full
    return None


# ---------------------------------------------------------------------------
# 검색 (KO/EN 키워드 스코어링)
# ---------------------------------------------------------------------------
GRAPH_HOP_TOP = 5      # 1-hop 확장을 적용할 상위 히트 수
GRAPH_HOP_DECAY = 0.3  # 1-hop 이웃의 점수 감쇠 계수

STOPWORDS = {
    "그리고", "하지만", "그래서", "어떻게", "무엇", "뭐야", "뭔지", "알려줘", "있어", "없어",
    "어디", "언제", "누가", "왜", "이거", "우리", "관련", "대해", "대한", "정리", "설명",
    "the", "and", "for", "with", "what", "how", "why", "when", "where", "which", "this",
    "that", "are", "is", "of", "to", "in", "on", "a", "an", "do", "does", "about",
}


# 한↔영 동의어 그룹 — 질의 토큰 확장 전용 (문서 인덱싱에는 미적용).
# 주의1: 매칭이 substring이라 3글자 미만 영문 alias("ad" 등)는 오탐 — 금지.
# 주의2: 다른 그룹 단어의 substring인 alias(date⊂update 등)는
#        WORD_BOUNDED_ALIASES에 등록해 단어 경계로만 매칭할 것 (교차 그룹 오탐 방지).
ALIAS_GROUPS = [
    ("아내", "와이프", "wife"),
    ("남편", "husband"),
    ("결혼", "웨딩", "marriage", "wedding"),
    ("기념일", "anniversary"),
    ("생일", "birthday"),
    ("여행", "trip", "travel"),
    ("데이트", "date"),
    ("음식", "food"),
    ("커피", "카페", "coffee"),
    ("영화", "movie"),
    ("선물", "gift", "present"),
    ("사랑", "love"),
    ("약속", "promise"),
    ("다툼", "싸움", "갈등", "conflict", "fight"),
    ("화해", "사과", "reconcile"),
    ("강아지", "반려견", "dog"),
    ("집", "house", "home"),
    ("이사", "moving"),
    ("회사", "직장", "office"),
    ("돈", "money", "budget"),
    ("건강", "health"),
    ("취향", "preference"),
    ("별명", "애칭", "nickname"),
    ("추억", "기억", "memory"),
    ("프로포즈", "프러포즈", "proposal"),
    ("상견례", "양가"),
    ("부모님", "parents"),
    ("운동", "exercise"),
    ("요리", "cooking"),
    ("청소", "cleaning"),
    ("규칙", "rule"),
    ("계획", "plan"),
    ("연애", "dating"),
    ("신혼", "newlywed"),
]

# 양방향 alias 맵: 토큰 → 같은 그룹의 나머지 토큰들
_ALIAS_MAP = {}
for _grp in ALIAS_GROUPS:
    for _w in _grp:
        _ALIAS_MAP.setdefault(_w, []).extend(x for x in _grp if x != _w)


def expand_kws(kws):
    """질의 토큰에 한↔영 alias를 덧붙인다 (순서 보존·중복 제거)."""
    out = []
    for kw in kws:
        out.append(kw)
        out.extend(_ALIAS_MAP.get(kw, ()))
    return list(dict.fromkeys(out))


def tokenize(text):
    text = (text or "").lower()
    # 영문/숫자 ↔ 한글 경계에 공백 삽입 → 'youtube랑'·'instagram는'·'kakao에서'
    # 처럼 조사가 붙은 토큰을 영문 키워드와 한글로 분리 (검색 매칭율 개선)
    text = re.sub(r"([a-z0-9_])([가-힣])", r"\1 \2", text)
    text = re.sub(r"([가-힣])([a-z0-9_])", r"\1 \2", text)
    out = []
    for w in re.findall(r"[a-z0-9_가-힣\-]+", text):
        if w not in STOPWORDS and len(w) >= 2:
            out.append(w)
    return list(dict.fromkeys(out))


# 교차 그룹 substring 충돌 alias — 단어 경계로만 매칭 (date⊂update/candidate 오탐 방지).
# 경계 = 영문/숫자 인접 금지. 하이픈/언더스코어/한글 인접은 허용.
# 나머지 alias는 substring 유지 — dog→doggy, love→lovely 같은 recall 보존.
WORD_BOUNDED_ALIASES = {"date"}
_WORD_BOUNDED_RE = {
    w: re.compile(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])")
    for w in WORD_BOUNDED_ALIASES
}


def kw_in_text(low_text, kw):
    """kw 존재 여부 — 단어 경계 대상 kw는 경계 매칭, 나머지는 substring."""
    pat = _WORD_BOUNDED_RE.get(kw)
    if pat is None:
        return kw in low_text
    return kw in low_text and pat.search(low_text) is not None


def kw_count(low_text, kw):
    """kw 출현 횟수 — 단어 경계 대상 kw는 경계 매칭, 나머지는 substring."""
    pat = _WORD_BOUNDED_RE.get(kw)
    if pat is None:
        return low_text.count(kw)
    if kw not in low_text:   # substring 선검사로 정규식 전체 스캔 회피
        return 0
    return len(pat.findall(low_text))


def kw_find(low_text, kw):
    """kw 첫 매치 위치(-1=없음) — 단어 경계 대상 kw는 경계 매칭, 나머지는 substring."""
    pat = _WORD_BOUNDED_RE.get(kw)
    if pat is None:
        return low_text.find(kw)
    if kw not in low_text:
        return -1
    m = pat.search(low_text)
    return m.start() if m else -1


def kws_in_doc(low_text, kws):
    return [kw for kw in kws if kw_in_text(low_text, kw)]


def excerpt_around(text, kws, span=700):
    """첫 키워드 매치 주변 발췌."""
    low = text.lower()
    pos = -1
    for kw in kws:
        p = kw_find(low, kw)
        if p != -1 and (pos == -1 or p < pos):
            pos = p
    if pos == -1:
        return text[:span].strip()
    start = max(0, pos - span // 3)
    end = min(len(text), pos + span)
    return ("…" if start > 0 else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def search(query, k_wiki=12, k_raw=10, wiki_nodes=None, raw_docs=None):
    """질의 → (wiki_hits, raw_hits). wiki_hits=[(score,node)], raw_hits=[(score,doc,text)]."""
    if wiki_nodes is None:
        wiki_nodes = load_wiki_nodes()
    if raw_docs is None:
        raw_docs = list_raw_docs()
    kws = expand_kws(tokenize(query))   # 질의 토큰에만 alias 확장 (문서 인덱싱 불변)
    if not kws:
        return [], []

    scored_wiki = []
    for n in wiki_nodes:
        tldr, tagtext, body, slug = n["tldr"].lower(), " ".join(n["tags"]).lower(), n["body"].lower(), n["slug"].lower()
        score = 0.0
        for kw in kws:
            if kw_in_text(slug, kw):
                score += 6
            if kw_in_text(tldr, kw):
                score += 8
            if kw_in_text(tagtext, kw):
                score += 5
            if kw_in_text(body, kw):
                score += 3
        if score > 0:
            scored_wiki.append((score, n))
    scored_wiki.sort(key=lambda x: x[0], reverse=True)

    # 그래프 1-hop 확장 — 직접 히트에 먼저 k 컷을 적용하고, 이웃은 잔여 슬롯에만
    # 감쇠 점수(최고점 부모 기준 1회)로 합류시킨다. 키워드를 실제 포함한 직접 히트가
    # hop-only 노드에 밀려 탈락하는 일을 방지. dangling 링크([[ghost]])는 무시,
    # 이미 히트된 노드는 중복 추가 금지. 합류 이웃의 링크는 재확장 안 함(1-hop 한정).
    wiki_hits = scored_wiki[:k_wiki]
    slots = k_wiki - len(wiki_hits)
    if wiki_hits and slots > 0:
        by_slug = {n["slug"]: n for n in wiki_nodes}
        hit_slugs = {n["slug"] for _, n in wiki_hits}
        hop_hits = []
        for score, n in wiki_hits[:GRAPH_HOP_TOP]:
            for target, _rel in n["links"]:
                if target in by_slug and target not in hit_slugs:
                    hit_slugs.add(target)
                    hop_hits.append((score * GRAPH_HOP_DECAY, by_slug[target]))
        hop_hits.sort(key=lambda x: x[0], reverse=True)
        wiki_hits = wiki_hits + hop_hits[:slots]
        wiki_hits.sort(key=lambda x: x[0], reverse=True)

    scored_raw = []
    for d in raw_docs:
        full = os.path.join(BRAIN_DIR, d["path"])
        cached = _RAW_CACHE.get(full)
        if cached is not None:
            # 직전 list_raw_docs()가 스탬프를 갱신했으므로 캐시 본문 재사용 (이중 read 제거)
            text, low = cached[2], cached[3]
        else:
            try:
                text = _read(full)
            except Exception:
                continue
            low = text.lower()
        hits = sum(kw_count(low, kw) for kw in kws)
        if hits > 0:
            score = hits * 2 + min(len(kws_in_doc(low, kws)) * 3, 15)
            scored_raw.append((score, d, text))
    scored_raw.sort(key=lambda x: x[0], reverse=True)
    return wiki_hits, scored_raw[:k_raw]
