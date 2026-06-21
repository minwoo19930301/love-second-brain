# -*- coding: utf-8 -*-
"""
Love Second Brain — 로컬 대시보드 + RAG 챗봇.

raw/(불변 원본: 카카오톡 대화) + wiki/(정제 노드)를 종합해 대시보드·지식그래프·노드탐색기·원본뷰어·
AI RAG 챗봇을 제공한다. 챗봇은 Claude CLI(claude -p, 구독/SSO 인증)를 subprocess로 호출한다.
CLI 없으면 키워드 검색 폴백으로 동작.

실행:  python3 app/server.py [port]   (기본 8080)  →  http://localhost:8080
의존성 없음 — Python 3 표준 라이브러리만 사용.
"""
import os
import re
import sys
import json
import shutil
import datetime
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain  # noqa: E402  (공유 데이터 레이어)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else int(os.environ.get("PORT", "8080"))

CLAUDE_TIMEOUT      = int(os.environ.get("CLAUDE_TIMEOUT", "120"))
CLAUDE_MODEL        = os.environ.get("CLAUDE_MODEL", "")

SYSTEM_PROMPT = (
    "너는 나와 상대의 카카오톡 대화에서 정제한 'Love Second Brain' 어시스턴트야. "
    "아래 [컨텍스트]로 제공된 노트/대화 발췌에만 근거해서 한국어로 따뜻하고 정확하게 답해.\n"
    "규칙:\n"
    "1. 컨텍스트에 있는 내용만 사용해. 추측하거나 지어내지 마. "
    "없으면 '아직 브레인에 정리돼 있지 않아'라고 말해.\n"
    "2. 답변 끝에 근거 경로를 `[출처: <path>]` 형식으로 밝혀.\n"
    "3. 마크다운(볼드·리스트) 사용 가능. 간결하되 핵심은 빠짐없이.\n"
    "4. 도구를 사용하지 말고, 제공된 컨텍스트만으로 한 번에 답해.\n"
)


def find_claude_bin():
    env = os.environ.get("CLAUDE_BIN")
    if env and os.path.exists(env) and os.access(env, os.X_OK):
        return env
    found = shutil.which("claude")
    if found:
        return found
    home = os.path.expanduser("~")
    for c in [
        os.path.join(home, ".local/bin/claude"),
        os.path.join(home, ".claude/local/claude"),
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
        os.path.join(home, ".npm-global/bin/claude"),
    ]:
        if os.path.exists(c) and os.access(c, os.X_OK):
            return c
    return None


def build_context(wiki_hits, raw_hits, question):
    kws = brain.expand_kws(brain.tokenize(question))   # 발췌 위치 탐색도 search()와 동일하게 alias 확장
    parts = []
    citations = []
    if wiki_hits:
        parts.append("=== 정제 노드 (wiki) ===")
        for i, (score, n) in enumerate(wiki_hits, 1):
            citations.append(n["path"])
            body = n["body"][:1100] + "…" if len(n["body"]) > 1100 else n["body"]
            vt = brain.verified_tag(n)
            badge = f"{n['type']}·{vt}" if vt else n['type']
            parts.append(f"\n[노드 {i}] ({badge}) {n['slug']}\ntldr: {n['tldr']}\n{body}")
    if raw_hits:
        parts.append("\n=== 원본 소스 (raw) ===")
        for i, (score, d, text) in enumerate(raw_hits, 1):
            citations.append(d["path"])
            parts.append(f"\n[원본 {i}] {d['title']} <{d['path']}>\n{brain.excerpt_around(text, kws, 700)}")
    return "\n".join(parts), citations


def call_claude(question, context):
    claude_bin = find_claude_bin()
    if not claude_bin:
        return None, "claude CLI를 찾지 못했어요 (PATH 또는 CLAUDE_BIN 환경변수 확인)."
    prompt = f"{SYSTEM_PROMPT}\n[질문]\n{question}\n\n[컨텍스트]\n{context}\n"
    # 프롬프트는 인자가 아닌 stdin으로 전달 — Windows cmd.exe 8191자 명령줄 한도 회피
    cmd = [claude_bin, "-p", "--output-format", "text", "--max-turns", "1"]
    cwd, timeout = APP_DIR, CLAUDE_TIMEOUT
    if CLAUDE_MODEL:
        cmd += ["--model", CLAUDE_MODEL]
    try:
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)   # 구독/SSO 인증 사용, API key 강제 안 함
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout, cwd=cwd, env=env,
        )
        out = (proc.stdout or "").strip()
        if proc.returncode != 0 and not out:
            return None, f"claude 실행 실패 (code {proc.returncode}): {(proc.stderr or '')[:300]}"
        if not out:
            return None, "claude가 빈 응답을 반환했어요."
        return out, None
    except subprocess.TimeoutExpired:
        return None, f"claude 응답이 {timeout}s 안에 안 왔어요."
    except Exception as e:
        return None, f"claude 호출 오류: {e}"


# ---------------------------------------------------------------------------
# 카톡 채팅 통계 / grep — raw/chat/YYYY/YYYY-MM.md 스캔
# 월별 파일 한 줄 = 한 메시지: "HH:MM 나|아내: text". 날짜 헤더: "## YYYY-MM-DD (요일)".
# (parse_kakao.py write_month_files 포맷과 일치 — 멀티라인은 적재 시 한 줄로 접힘)
# ---------------------------------------------------------------------------
CHAT_DIR = os.path.join(brain.RAW_DIR, "chat")
_CHAT_MSG_RE = re.compile(r"^(\d{1,2}):(\d{2})\s+(나|아내):\s?(.*)$")
_CHAT_DATE_RE = re.compile(r"^##\s+(\d{4})-(\d{2})-(\d{2})")

_CHAT_STATS = None     # (signature, result) — 채팅 파일 mtime 시그니처로 캐시 무효화


def _chat_docs():
    """raw/chat/ 하위 월별 .md 문서 목록 (brain 캐시 활용, README/manifest 제외)."""
    brain.list_raw_docs()                         # _RAW_CACHE 갱신 (mtime 증분)
    out = []
    for full, entry in brain._RAW_CACHE.items():
        doc = entry[1]
        rel = doc["path"].replace("\\", "/")
        if not rel.startswith("raw/chat/"):
            continue
        base = os.path.basename(rel)
        if base in ("README.md", "manifest.md"):
            continue
        out.append((full, entry, doc))            # entry=(stamp, doc, text, low)
    return out


def _chat_signature():
    """채팅 파일 (경로, mtime_ns, size) 집합 — 하나라도 바뀌면 통계 재계산."""
    sig = []
    for full, entry, _doc in _chat_docs():
        sig.append((full, entry[0]))
    return tuple(sorted(sig))


def chat_stats():
    """카톡 통계: 발신자별·월별·연도별·시간대·요일 분포 + 헤드라인 수치."""
    global _CHAT_STATS
    sig = _chat_signature()
    if _CHAT_STATS is not None and _CHAT_STATS[0] == sig:
        return _CHAT_STATS[1]

    by_sender = {"나": 0, "아내": 0}
    chars = {"나": 0, "아내": 0}
    by_month, by_year, by_day = {}, {}, {}
    by_hour = {"나": [0] * 24, "아내": [0] * 24}
    by_weekday = [0] * 7                            # 0=월 … 6=일
    first_date, last_date = None, None

    for _full, entry, _doc in _chat_docs():
        text = entry[2]
        cur_ym = cur_year = cur_date = None
        cur_wd = None
        for ln in text.split("\n"):
            dm = _CHAT_DATE_RE.match(ln)
            if dm:
                y, mo, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
                cur_ym = "%04d-%02d" % (y, mo)
                cur_year = "%04d" % y
                cur_date = "%04d-%02d-%02d" % (y, mo, d)
                try:
                    cur_wd = datetime.date(y, mo, d).weekday()
                except ValueError:
                    cur_wd = None
                if first_date is None or cur_date < first_date:
                    first_date = cur_date
                if last_date is None or cur_date > last_date:
                    last_date = cur_date
                continue
            mm = _CHAT_MSG_RE.match(ln)
            if not mm:
                continue
            hh, sender, msg = int(mm.group(1)), mm.group(3), mm.group(4)
            if hh > 23 or cur_ym is None:
                continue
            by_sender[sender] += 1
            chars[sender] += len(msg)
            by_month.setdefault(cur_ym, {"나": 0, "아내": 0})[sender] += 1
            by_year.setdefault(cur_year, {"나": 0, "아내": 0})[sender] += 1
            by_hour[sender][hh] += 1
            if cur_wd is not None:
                by_weekday[cur_wd] += 1
            if cur_date is not None:
                by_day[cur_date] = by_day.get(cur_date, 0) + 1

    total = by_sender["나"] + by_sender["아내"]
    months = [{"month": k, "나": v["나"], "아내": v["아내"], "total": v["나"] + v["아내"]}
              for k, v in sorted(by_month.items())]
    years = [{"year": k, "나": v["나"], "아내": v["아내"], "total": v["나"] + v["아내"]}
             for k, v in sorted(by_year.items())]
    busiest_month = max(months, key=lambda m: m["total"]) if months else None
    busiest_day = (lambda kv: {"date": kv[0], "total": kv[1]})(
        max(by_day.items(), key=lambda x: x[1])) if by_day else None
    active_days = len(by_day)
    span = 0
    if first_date and last_date:
        try:
            a = datetime.date(*map(int, first_date.split("-")))
            b = datetime.date(*map(int, last_date.split("-")))
            span = (b - a).days + 1
        except ValueError:
            span = active_days

    result = {
        "total": total,
        "by_sender": by_sender,
        "chars_by_sender": chars,
        "by_month": months,
        "by_year": years,
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "first_date": first_date,
        "last_date": last_date,
        "days_span": span,
        "active_days": active_days,
        "avg_per_day": round(total / active_days, 1) if active_days else 0,
        "busiest_month": busiest_month,
        "busiest_day": busiest_day,
    }
    _CHAT_STATS = (sig, result)
    return result


def grep_chat(query, limit=400):
    """카톡 원본을 줄 단위로 즉석 검색(grep) — 공백 구분 토큰 AND 매칭(대소문자 무시).
    각 매치: 파일 경로·파일 내 메시지 인덱스(idx)·날짜·시각·발신자·본문. idx는 프론트 버블 순서와 일치."""
    tokens = [t for t in query.lower().split() if t]
    if not tokens:
        return {"query": query, "total": 0, "truncated": False, "results": []}
    results, total, truncated = [], 0, False
    for _full, entry, doc in _chat_docs():
        text = entry[2]
        cur_date = ""
        idx = -1
        for ln in text.split("\n"):
            dm = _CHAT_DATE_RE.match(ln)
            if dm:
                cur_date = "%s-%s-%s" % (dm.group(1), dm.group(2), dm.group(3))
                continue
            mm = _CHAT_MSG_RE.match(ln)
            if not mm:
                continue
            idx += 1
            msg = mm.group(4)
            low = msg.lower()
            if all(tok in low for tok in tokens):
                total += 1
                if len(results) < limit:
                    results.append({
                        "path": doc["path"], "idx": idx, "date": cur_date,
                        "time": "%s:%s" % (mm.group(1), mm.group(2)),
                        "sender": mm.group(3), "text": msg,
                    })
                else:
                    truncated = True
    results.sort(key=lambda r: (r["date"], r["time"]))
    return {"query": query, "total": total, "truncated": truncated, "results": results}


STATIC = {
    "/": ("index.html", "text/html"),
    "/index.html": ("index.html", "text/html"),
    "/index.css": ("index.css", "text/css"),
    "/app.js": ("app.js", "application/javascript"),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _host_ok(self):
        # DNS rebinding 방어 — Host 헤더가 loopback 호스트명일 때만 처리.
        # 127.0.0.1 바인딩은 '다른 머신'만 막고, 피해자 브라우저를 경유한 rebinding은
        # 못 막으므로 Host 검증으로 보강한다. (CORS 헤더도 안 붙임 — 로컬 전용)
        host = (self.headers.get("Host") or "").split(":")[0]
        if host in ("localhost", "127.0.0.1", "::1"):
            return True
        self.send_error(403, "Forbidden")
        return False

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, fn, ctype):
        path = os.path.join(APP_DIR, fn)
        if not os.path.exists(path):
            return self.send_error(404)
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_ok():
            return
        u = urlparse(self.path)
        path, query = u.path, parse_qs(u.query)
        if path in STATIC:
            return self._static(*STATIC[path])
        if path == "/api/stats":
            return self.api_stats()
        if path == "/api/chat_stats":
            return self._json(chat_stats())
        if path == "/api/grep":
            q = (query.get("q", [""])[0] or "").strip()
            return self._json(grep_chat(q))
        if path == "/api/graph":
            return self._json(brain.build_graph(brain.load_wiki_nodes()))
        if path == "/api/nodes":
            return self._json(brain.load_wiki_nodes())
        if path == "/api/raw":
            return self.api_raw(query)
        if path == "/api/health":
            return self._json({"claude_bin": find_claude_bin(), "ok": True})
        if path == "/api/domains":
            return self.api_domains()
        self.send_error(404)

    def do_POST(self):
        if not self._host_ok():
            return
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(raw)
        except Exception:
            return self._json({"error": "invalid json"}, 400)
        if u.path == "/api/chat":
            return self.api_chat(data)
        self.send_error(404)

    def api_stats(self):
        wiki = brain.load_wiki_nodes()
        raw = brain.list_raw_docs()
        graph = brain.build_graph(wiki)
        by_type, by_domain, tag_counts, raw_by_domain = {}, {}, {}, {}
        for n in wiki:
            by_type[n["type"]] = by_type.get(n["type"], 0) + 1
            by_domain[n["domain"]] = by_domain.get(n["domain"], 0) + 1
            for t in n["tags"]:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        for d in raw:
            raw_by_domain[d["domain"]] = raw_by_domain.get(d["domain"], 0) + 1
        real_slugs = {nn["slug"] for nn in graph["nodes"] if nn["type"] != "stub"}
        real_links = [l for l in graph["links"] if l["target"] in real_slugs]
        self._json({
            "raw_count": len(raw), "wiki_count": len(wiki), "edge_count": len(real_links),
            "by_type": by_type, "by_domain": by_domain, "raw_by_domain": raw_by_domain,
            "tags": sorted(tag_counts.items(), key=lambda x: x[1], reverse=True),
            "log": brain.parse_log(),
        })

    def api_chat(self, data):
        question = (data.get("question") or "").strip()
        if not question:
            return self._json({"error": "missing question"}, 400)
        wiki_hits, raw_hits = brain.search(question)
        if not wiki_hits and not raw_hits:
            return self._json({
                "answer": "관련 노드를 브레인에서 못 찾았어. 더 구체적인 키워드로 물어봐줘 "
                          "(예: '기념일', '아내 음식 취향', '둘만의 별명', '신혼여행').",
                "citations": [], "engine": "none",
            })
        context, citations = build_context(wiki_hits, raw_hits, question)
        answer, err = call_claude(question, context)
        if answer:
            return self._json({"answer": answer, "citations": citations, "engine": "claude"})
        # 폴백: claude 없거나 실패 → 검색 결과 직접 표시
        lines = [f"> ⚠️ claude CLI 응답 실패 → 키워드 검색 결과로 대신 안내합니다.",
                 f"> ({err})\n", f"### \"{question}\" 관련 노트\n"]
        for _, n in wiki_hits:
            lines.append(f"- **[{n['type']}] {n['slug']}** — {n['tldr']}  \n  `{n['path']}`")
        if raw_hits:
            lines.append("\n### 관련 원본")
            for _, d, _ in raw_hits:
                lines.append(f"- **{d['title']}**  \n  `{d['path']}`")
        self._json({"answer": "\n".join(lines), "citations": citations, "engine": "fallback"})

    CANONICAL_DOMAINS = ["person", "love", "taste", "events", "marriage", "rules", "lexicon", "life"]

    def api_domains(self):
        wiki = brain.load_wiki_nodes()
        raw = brain.list_raw_docs()
        domains = {d: {"wiki": [], "raw": []} for d in self.CANONICAL_DOMAINS}
        for n in wiki:
            d = n["domain"]
            if d not in domains:
                domains[d] = {"wiki": [], "raw": []}
            domains[d]["wiki"].append(n)
        for doc in raw:
            d = doc["domain"]
            if d not in domains:
                domains[d] = {"wiki": [], "raw": []}
            domains[d]["raw"].append(doc)
        # 정렬: 정규 도메인 순서 우선, 그 외(general 등)는 뒤에 알파벳
        order = {d: i for i, d in enumerate(self.CANONICAL_DOMAINS)}
        ordered = sorted(domains, key=lambda n: (order.get(n, 99), n))
        result = []
        for name in ordered:
            data = domains[name]
            nodes = data["wiki"]
            by_type = {}
            for n in nodes:
                by_type[n["type"]] = by_type.get(n["type"], 0) + 1
            tag_counts = {}
            for n in nodes:
                for t in n["tags"]:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:7]
            recent = sorted([n for n in nodes if n["updated"]], key=lambda n: n["updated"], reverse=True)[:4]
            if not recent:
                recent = nodes[:4]
            result.append({
                "name": name,
                "wiki_count": len(nodes),
                "raw_count": len(data["raw"]),
                "by_type": by_type,
                "tags": [[t, c] for t, c in top_tags],
                "recent_nodes": [{"slug": n["slug"], "type": n["type"], "tldr": n["tldr"], "updated": n["updated"]} for n in recent],
                "raw_docs": [{"title": doc["title"], "path": doc["path"]} for doc in data["raw"]],
            })
        self._json(result)

    def api_raw(self, query):
        p = query.get("path", [None])[0]
        if not p:
            return self._json(brain.list_raw_docs())
        full = brain.safe_join(p)
        if not full:
            return self._json({"error": "not found"}, 404)
        self._json({"path": p, "content": brain._read(full)})


def main():
    print("=" * 60)
    print(f"  Love Second Brain (대시보드)  →  http://localhost:{PORT}")
    print(f"  브레인: {brain.BRAIN_DIR}")
    wiki = brain.load_wiki_nodes()
    raw  = brain.list_raw_docs()
    cb   = find_claude_bin()
    print(f"  raw/: {len(raw)} docs   wiki/: {len(wiki)} nodes")
    if cb:
        print(f"  RAG: claude CLI 발견 → {cb}")
    else:
        print("  RAG: ⚠️ claude CLI 없음 — 챗봇은 키워드 검색 폴백으로 동작.")
        print("       (PATH에 claude 추가하거나  CLAUDE_BIN=/path/to/claude  설정)")
    print("  종료: Ctrl+C")
    print("=" * 60, flush=True)
    # 127.0.0.1만 바인딩 — 로컬 전용 대시보드(외부 망 노출 차단). 공유는 각자 자기 머신에서 기동.
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
