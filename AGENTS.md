# AI Agent Instruction Manual (AGENTS.md)

이 파일은 **Love Second Brain**(연인·부부 지식 베이스)을 다루는 AI 코딩 에이전트(Claude Code, Gemini, Cursor 등)용 지침입니다.

---

## 1. 데이터 소스 — 카카오톡 대화 (KakaoTalk)

이 브레인의 1차 원본은 카카오톡 대화 export(`.txt`)입니다.

### A. 파싱·적재 (raw 만들기)

카톡 export 폴더(들)를 [`scripts/parse_kakao.py`](scripts/parse_kakao.py)에 넘기면, 정규화된 월별 마크다운을 `raw/chat/YYYY/YYYY-MM.md`로 적재하고 `raw/chat/manifest.md`(기간·메시지 통계)를 만든다.

```bash
SB_ME_NAMES="<본인 카톡 표시이름>" python3 scripts/parse_kakao.py "<export폴더1>" "<export폴더2>" ...
# 출력: raw/chat/YYYY/*.md  +  raw/chat/manifest.md  +  raw/chat/README.md
```

- 입력 카톡 원본 txt 자체는 repo 밖(예: ~/Downloads)에 두고, **정규화본만** `raw/chat/`에 둔다(공개 repo면 데이터는 커밋 금지 — `.gitignore` 참고).
- 발신자는 `나`(본인) / `아내`(상대; 1:1 대화 가정)로 정규화된다. **본인 카톡 표시이름은 환경변수 `SB_ME_NAMES`로 지정** — 그 이름만 `나`, 나머지는 상대가 된다.
- `raw/chat/`은 **불변** — 파싱 결과를 손으로 고치지 않는다.

### B. 정제 (raw → wiki)

`raw/chat/`을 읽고 지속적 지식만 atomic 노드로 정제한다. 절차·강화 규칙은 [`.claude/skills/distill/SKILL.md`](.claude/skills/distill/SKILL.md), 규약은 [`schema.md`](schema.md).

- **남길 것(지속적 지식):** 취향(좋아함/싫어함)·약속·둘만의 은어/별명·기념일과 사건·함께 내린 결정·인물 특징.
- **버릴 것(휘발성):** 일상 잡담, 그때만 유효한 약속(점심 메뉴 정하기), 단순 안부.
- 카톡 한 토막의 농담을 사실로 단정하지 말 것 — 취향·감정 추정은 `verified: provisional`, 본인 확인 후 `domain-expert-verified`(+`verified_by`).

---

## 2. 토큰 사용 절약 (대용량 대화 스캔)

카톡 대화는 보통 수만~수십만 줄이라 한 번에 다 읽으면 컨텍스트가 넘친다.
- **월/연 단위로 청크해서** 읽는다 (`raw/chat/YYYY/YYYY-MM.md` 한 파일씩).
- 먼저 `raw/chat/manifest.md`로 기간·분량을 파악하고, 의미 있는 구간(연애 초기·결혼 준비·신혼 등)부터 정제한다.

---

## 3. 외부 자료 (사진·캡처 등)

카톡에 텍스트로 안 남은 맥락(사진, 청첩장 등)은 **스크린샷을 보여주고** 정리를 요청한다.

---

## 4. Copy-Paste Agent Training Prompt

새 세션을 시작할 때 아래를 복붙:

```text
You are an AI agent working on a personal "couple second brain" — KakaoTalk chat distilled into a markdown knowledge base:
- raw/chat/YYYY/ : immutable normalized KakaoTalk logs (month per file). Never edit.
- wiki/<domain>/ : distilled atomic nodes (claim/concept/decision/source/person/event),
  connected with standard markdown links [label](path.md). Follow schema.md.
- Domains: person, love, taste, events, marriage, rules, lexicon, life.

Rules of engagement:
1. The data is private and personal — be accurate and respectful. Cite raw/chat paths.
2. Read in month-sized chunks; check raw/chat/manifest.md first to scope the timeline.
3. Keep durable knowledge (tastes, promises, in-jokes, anniversaries, decisions, traits);
   drop ephemeral chatter. Don't treat a single joke as fact.
4. Tastes/emotions/intent are interpretive → verified: provisional until the person confirms
   (then domain-expert-verified + verified_by).
5. No index/build step — the dashboard app and MCP server detect file changes via mtime.
   After adding/updating nodes, append one line to log.md.
6. When distilling, follow .claude/skills/distill and make sure
   `python3 scripts/distill_lint.py <node paths...>` exits 0 before finishing.
```
