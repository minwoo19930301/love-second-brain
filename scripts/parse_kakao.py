#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
카카오톡 대화 export(.txt) → raw/chat/ 정규화 적재.

KakaoTalk(맥/PC) 대화 내보내기 포맷을 파싱해 월별 마크다운으로 떨군다:
  - raw/chat/YYYY/YYYY-MM.md  (월별 대화, 불변 원본)
  - raw/chat/manifest.md      (기간·메시지 통계)
  - raw/chat/README.md        (출처 설명)

발신자는 `나`(본인) / `아내`(상대; 1:1 대화 가정)로 정규화한다.
본인의 카톡 표시이름은 환경변수 SB_ME_NAMES(콤마 구분)로 지정한다.
서로 다른 export 파일에 같은 메시지가 겹치면(시각·발신자·본문 동일) 한 번만 남긴다.

의존성 없음 — Python 3 표준 라이브러리만.

사용법:
    SB_ME_NAMES="홍길동" python3 scripts/parse_kakao.py "<export폴더1>" "<export폴더2>" ...
    (또는 SB_CHAT_DIRS="<폴더1>,<폴더2>" 환경변수로 폴더 지정)
"""
import os
import re
import sys
import glob
import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN_DIR = os.path.dirname(_HERE)
OUT_DIR = os.path.join(BRAIN_DIR, "raw", "chat")

# 발신자 정규화 — 본인 카톡 표시이름만 '나', 나머지 발신자는 모두 상대(아내)로 수렴(1:1 대화 가정).
ME = "나"
WIFE = "아내"
# 본인의 카카오톡 표시이름(들)을 환경변수 SB_ME_NAMES에 콤마로 지정. (예: SB_ME_NAMES="홍길동,Gildong")
# 비워두면 모든 발신자가 '아내(상대)'로 분류되니 반드시 본인 이름을 넣어 주세요.
ME_NAMES = {n.strip() for n in os.environ.get("SB_ME_NAMES", "").split(",") if n.strip()}

# 카톡 export 폴더(들). 환경변수 SB_CHAT_DIRS(콤마 구분) 또는 CLI 인자로 지정.
DEFAULT_FOLDERS = [os.path.expanduser(p.strip())
                   for p in os.environ.get("SB_CHAT_DIRS", "").split(",") if p.strip()]

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 2019. 5. 7. 오전 10:16, 홍길동 : 오늘 점심 먹을래?
MSG_RE = re.compile(
    r"^(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(오전|오후)\s*(\d{1,2}):(\d{2}),\s*(.+?)\s*:\s?(.*)$"
)
# 2019년 5월 7일 화요일
DATE_HDR_RE = re.compile(r"^\d{4}년\s*\d{1,2}월\s*\d{1,2}일")


def to_24h(ampm, hour):
    """오전/오후 + 12시간제 시각 → 24시간제 시각."""
    hour = int(hour)
    if ampm == "오전":
        return 0 if hour == 12 else hour
    return 12 if hour == 12 else hour + 12


def normalize_sender(raw):
    """카톡 발신자 → '나' / '아내'. ME_NAMES(SB_ME_NAMES)에 속한 이름만 '나', 그 외는 모두 상대(아내)."""
    raw = raw.strip()
    if raw in ME_NAMES:
        return ME
    return WIFE


def iter_messages(path):
    """한 export 파일 → (datetime, sender_raw, text) 제너레이터. 멀티라인 메시지는 병합."""
    cur = None  # [dt, sender_raw, [text_lines...]]
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n").lstrip("﻿")
            m = MSG_RE.match(line)
            if m:
                if cur is not None:
                    yield cur[0], cur[1], "\n".join(cur[2]).strip()
                y, mo, d, ampm, hh, mm, sender, text = m.groups()
                try:
                    dt = datetime.datetime(int(y), int(mo), int(d), to_24h(ampm, hh), int(mm))
                except ValueError:
                    cur = None
                    continue
                cur = [dt, sender, [text]]
            elif DATE_HDR_RE.match(line):
                # 날짜 구분 헤더 — 메시지 경계. 진행 중 메시지를 닫는다.
                if cur is not None:
                    yield cur[0], cur[1], "\n".join(cur[2]).strip()
                    cur = None
            else:
                # 타임스탬프 없는 줄 = 직전 메시지의 다음 줄(멀티라인) 또는 파일 머리 잡음.
                if cur is not None:
                    cur[2].append(line)
    if cur is not None:
        yield cur[0], cur[1], "\n".join(cur[2]).strip()


def collect(folders):
    """폴더들의 Talk_*.txt를 모두 읽어 (dt, sender_norm, text) 리스트 + 통계 반환.
    서로 다른 파일에 같은 (dt, sender, text)가 겹치면 한 번만 남긴다(cross-file dedup)."""
    files = []
    for folder in folders:
        if os.path.isfile(folder) and folder.endswith(".txt"):
            files.append(folder)
        elif os.path.isdir(folder):
            files.extend(sorted(glob.glob(os.path.join(folder, "*.txt")),
                                key=_natural_key))
    seen = {}            # (dt, sender, text) -> 처음 등장한 파일
    msgs = []            # (dt, sender_norm, text, seq)
    dup_dropped = 0
    seq = 0
    for path in files:
        for dt, sender_raw, text in iter_messages(path):
            if not text:
                continue
            sender = normalize_sender(sender_raw)
            key = (dt, sender, text)
            if key in seen and seen[key] != path:
                dup_dropped += 1
                continue
            seen.setdefault(key, path)
            msgs.append((dt, sender, text, seq))
            seq += 1
    msgs.sort(key=lambda x: (x[0], x[3]))   # 시각 우선, 동시각은 등장 순서 보존
    return msgs, files, dup_dropped


def _natural_key(path):
    """'Talk_...-10.txt'의 끝 숫자를 자연 정렬용 키로."""
    base = os.path.basename(path)
    nums = re.findall(r"(\d+)", base)
    return [int(n) for n in nums] if nums else [0]


def _oneline(text):
    """월별 파일 한 줄 표기용 — 내부 줄바꿈은 공백으로 접는다."""
    return re.sub(r"\s*\n\s*", "  ", text).strip()


def write_month_files(msgs):
    """월별로 그룹핑해 raw/chat/YYYY/YYYY-MM.md 작성. {('YYYY-MM'): count} 반환."""
    by_month = {}
    for dt, sender, text, _ in msgs:
        by_month.setdefault((dt.year, dt.month), []).append((dt, sender, text))
    month_counts = {}
    for (y, mo), items in sorted(by_month.items()):
        ym = "%04d-%02d" % (y, mo)
        ydir = os.path.join(OUT_DIR, "%04d" % y)
        os.makedirs(ydir, exist_ok=True)
        lines = [
            "# %d년 %d월 카카오톡 대화" % (y, mo),
            "",
            "> 나 ❤️ 너 — 카카오톡 대화 원본(정규화). 불변(raw). 발신자: `나`=본인, `아내`=상대.",
            "",
        ]
        cur_day = None
        for dt, sender, text in items:
            if dt.date() != cur_day:
                cur_day = dt.date()
                wd = WEEKDAY_KO[dt.weekday()]
                lines.append("\n## %s (%s)" % (cur_day.isoformat(), wd))
            lines.append("%02d:%02d %s: %s" % (dt.hour, dt.minute, sender, _oneline(text)))
        with open(os.path.join(ydir, ym + ".md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        month_counts[ym] = len(items)
    return month_counts


def write_manifest(msgs, files, dup_dropped, month_counts):
    n = len(msgs)
    n_me = sum(1 for _, s, _, _ in msgs if s == ME)
    n_wife = n - n_me
    first, last = msgs[0][0], msgs[-1][0]
    lines = [
        "# 카카오톡 대화 manifest",
        "",
        "> `scripts/parse_kakao.py`가 생성한 적재 통계. 정제(distill) 청킹의 길잡이.",
        "",
        "## 요약",
        "- 기간: **%s ~ %s**" % (first.date().isoformat(), last.date().isoformat()),
        "- 총 메시지: **%d개** (나 %d · 아내 %d)" % (n, n_me, n_wife),
        "- cross-file 중복 제거: %d개" % dup_dropped,
        "- 소스 파일: %d개" % len(files),
        "",
        "## 월별 메시지 수",
        "",
        "| 연-월 | 메시지 |",
        "|------|------:|",
    ]
    for ym in sorted(month_counts):
        lines.append("| %s | %d |" % (ym, month_counts[ym]))
    lines += ["", "## 소스 파일", ""]
    for p in files:
        lines.append("- `%s`" % os.path.basename(p))
    with open(os.path.join(OUT_DIR, "manifest.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_readme():
    txt = (
        "# raw/chat — 카카오톡 대화 원본\n\n"
        "나와 상대의 카카오톡 대화 export를 `scripts/parse_kakao.py`로 정규화한 **불변 원본**입니다.\n\n"
        "- `YYYY/YYYY-MM.md` — 월별 대화. `HH:MM 나|아내: 메시지` 한 줄씩.\n"
        "- `manifest.md` — 기간·메시지 통계(정제 청킹용).\n\n"
        "**수정 금지** — 정제 지식은 `wiki/<도메인>/`에 atomic 노드로 만듭니다(`schema.md`).\n"
        "원본 export txt 자체는 repo 밖(개인 보관)에 두고, 정규화본만 커밋합니다.\n"
    )
    with open(os.path.join(OUT_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write(txt)


def main(argv):
    folders = argv[1:] if len(argv) > 1 else DEFAULT_FOLDERS
    folders = [f for f in folders if os.path.exists(f)]
    if not folders:
        print("사용법: SB_ME_NAMES=\"홍길동\" python3 scripts/parse_kakao.py \"<export폴더>\" [...]", file=sys.stderr)
        print("(또는 SB_CHAT_DIRS 환경변수로 폴더 지정 — 둘 다 비어서 폴더를 못 찾음)", file=sys.stderr)
        return 2
    if not ME_NAMES:
        print("⚠ 본인 카톡 이름이 설정되지 않았습니다 — 모든 메시지가 '아내(상대)'로 분류됩니다.", file=sys.stderr)
        print("  환경변수로 본인 이름을 지정하세요:  SB_ME_NAMES=\"<카톡 표시이름>\"", file=sys.stderr)
    os.makedirs(OUT_DIR, exist_ok=True)
    msgs, files, dup_dropped = collect(folders)
    if not msgs:
        print("메시지를 하나도 파싱하지 못했습니다. 폴더/포맷을 확인하세요.", file=sys.stderr)
        return 1
    month_counts = write_month_files(msgs)
    write_manifest(msgs, files, dup_dropped, month_counts)
    write_readme()
    print("적재 완료: %d개 메시지, %d개 월파일 (%s ~ %s), 중복 %d개 제거"
          % (len(msgs), len(month_counts),
             msgs[0][0].date().isoformat(), msgs[-1][0].date().isoformat(), dup_dropped))
    print("→ %s" % OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
