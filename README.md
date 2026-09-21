# 💗 Love Second Brain

<!-- PROJECT-PRESENTATION:START -->
<a href="https://github.com/minwoo19930301/love-second-brain"><img src=".github/project-cover.svg" alt="💗 Love Second Brain" width="960"></a>

[![QUICK START](https://img.shields.io/badge/QUICK%20START-374151?style=for-the-badge)](#-시작하기--비어-있는-repo를-데이터로-채우기) [![SOURCE](https://img.shields.io/badge/SOURCE-444444?style=for-the-badge)](https://github.com/minwoo19930301/love-second-brain)
<!-- PROJECT-PRESENTATION:END -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![GitHub stars](https://img.shields.io/github/stars/minwoo19930301/love-second-brain?style=social)](https://github.com/minwoo19930301/love-second-brain/stargazers)

연인·부부의 **카카오톡 대화**를 **사람과 AI가 같이 읽고 채우는** 우리 둘만의 지식 베이스.
`raw/`(불변 원본: 카톡 대화) → `wiki/`(정제된 atomic 노드, 마크다운 링크로 연결) → 핑크빛 대시보드 + AI 질의응답(RAG).

> 이 repo는 **빈 껍데기(템플릿)** 입니다. 데이터는 직접 채웁니다 — 그리고 그 채우는 일을 **AI 에이전트(Claude 등)에게 시키면** 됩니다.
> 의존성 없음 — **Python 3 표준 라이브러리만** 사용.

<p align="center"><em>총 메시지 · 누가 더 많이 보냈나 · 월별/시간대/요일 분포 · 카톡 스타일 채팅 뷰어 · 전체 대화 즉석 grep 검색 · 지식 그래프</em></p>

---

## 🚀 시작하기 — 비어 있는 repo를 데이터로 채우기

이 repo엔 **코드만** 들어 있고 대화 데이터(`raw/`, `wiki/`)는 비어 있습니다.
가장 쉬운 길은 **이 폴더를 AI 코딩 에이전트(Claude Code / Claude 데스크톱 / Cursor 등)로 열고, 아래를 그대로 시키는 것**입니다.

### 0. 이 폴더를 AI 에이전트로 연다
Claude Code(터미널)·Claude 데스크톱·Cursor 중 편한 걸로 이 repo 폴더를 엽니다.
에이전트가 [`AGENTS.md`](AGENTS.md)·[`CLAUDE.md`](CLAUDE.md)·[`schema.md`](schema.md)를 먼저 읽고 규약대로 일합니다.

### 1. 카카오톡 대화 내보내기 (export)
- **PC(맥/윈도우) 카카오톡**: 대화방 → 메뉴 → **대화 내용 내보내기 → 텍스트(.txt)**.
- **모바일**: 대화방 → 설정(≡) → **대화 내용 내보내기 → 텍스트** → 파일을 PC로 옮깁니다.
- 내보낸 `.txt`(들)는 **repo 밖**(예: `~/Downloads`)에 둡니다. 원문 txt는 커밋하지 않습니다(아래 *프라이버시* 참고).

### 2. 에이전트에게 "수집(ingest)"을 시킨다
에이전트에게 이렇게 말하세요:

> **"`~/Downloads/<내보낸 카톡 폴더>`를 `scripts/parse_kakao.py`로 `raw/chat/`에 정규화 적재해줘.
> 내 카톡 표시이름은 `<여기에 본인 이름>` 이야."**

내부적으로 이렇게 실행됩니다 (직접 돌려도 됩니다):
```bash
SB_ME_NAMES="<내 카톡 표시이름>" python3 scripts/parse_kakao.py "~/Downloads/<카톡 export 폴더>" [...]
# → raw/chat/YYYY/YYYY-MM.md (월별 정규화) + raw/chat/manifest.md (통계)
```
> `나`(본인) / `아내`(상대)로 정규화됩니다. 본인 이름(`SB_ME_NAMES`)만 `나`, 나머지는 상대가 됩니다(1:1 대화 가정).

### 3. 에이전트에게 "정제(distill)"를 시킨다
> **"`raw/chat`을 월 단위로 읽고, 지속적 지식만 `wiki/<도메인>/`에 atomic 노드로 정리해줘. `schema.md` 규약 따라서."**

에이전트가 취향·약속·둘만의 은어/별명·기념일·함께 내린 결정·인물 특징을 노드로 뽑아 마크다운 링크로 연결합니다.
(휘발성 잡담은 버립니다. 자세한 절차는 [`AGENTS.md`](AGENTS.md) / [`.claude/skills/distill`](.claude/skills/distill/SKILL.md).)

### 4. 둘러보기 & 물어보기
```bash
python3 app/server.py            # → http://localhost:8080
```
- **대시보드**: 총 메시지·누가 더 많이 보냈나·월별/연도별/시간대/요일 분포
- **원본 소스**: 카톡 스타일 채팅 버블 + **전체 대화 즉석 grep 검색**(AI 아님, 클릭하면 그 대화로 점프)
- **지식 그래프 · 노드 탐색기 · 도메인 뷰**
- **AI 질의응답**: 챗봇이 `claude -p`(구독 인증)로 brain 근거 기반 답변 (claude CLI 없으면 키워드 검색 폴백)

또는 이 폴더를 Claude/Cursor로 열면 [`.mcp.json`](.mcp.json)의 `love-brain` MCP 서버가 자동 연결돼, AI가 brain을 검색·인용합니다(설치·API key 불필요). 자세히는 [`CLAUDE.md`](CLAUDE.md).

---

## 📋 에이전트에게 그대로 붙여넣는 프롬프트

```text
이 repo는 "Love Second Brain" 템플릿이야. AGENTS.md·CLAUDE.md·schema.md를 먼저 읽어.
내 카카오톡 대화 export 폴더는 <경로>이고, 내 카톡 표시이름은 <이름>이야.
1) scripts/parse_kakao.py로 raw/chat/에 정규화 적재해줘 (SB_ME_NAMES=<이름>).
2) raw/chat을 월 단위로 읽고 wiki/<도메인>/에 atomic 노드로 정제해줘 (schema.md 규약, distill 스킬).
3) 끝나면 python3 scripts/distill_lint.py <만든 노드 경로...> 가 통과하는지 확인하고, log.md에 한 줄 남겨줘.
```

---

## 📂 구조

- `raw/<도메인>/` — **불변 원본**(카톡 월별 대화 `raw/chat/YYYY/`). source of truth, 수정 안 함.
- `wiki/<도메인>/` — **정제 atomic 노드**(`claim`·`concept`·`decision`·`source`·`person`·`event`). 마크다운 링크 `[표시](경로.md)` = 엣지.
- 도메인: `person · love · taste · events · marriage · rules · lexicon · life`.
- `app/` — 시각화 대시보드 + RAG 챗봇 / `mcp-server/` — MCP 서버 / `scripts/` — 적재·정제 도구 / `templates/` — 노드 템플릿.
- 흐름: `raw(원본) → distill(정제) → wiki(노드) → query(질의)`.

## 🔒 프라이버시

이건 **당신 둘의 사적인 기록**입니다. 안전하게 다루도록 설계돼 있습니다:

- 카톡 원문 txt와 정규화된 `raw/chat/**`, 정제된 `wiki/**` 노드는 [`.gitignore`](.gitignore)로 **기본 커밋 제외**됩니다. 실수로 개인 대화가 push되지 않습니다.
- 대시보드 서버는 **127.0.0.1 로컬 전용** 바인딩(외부 망 노출 차단).
- 공개 repo로 쓸 거면 데이터를 절대 커밋하지 말고, 진짜로 비공개로 보관하려면 **private repo**를 쓰세요.

> 데이터를 정말 repo에 함께 보관하고 싶다면(개인 백업용 private repo), `.gitignore`에서 해당 라인을 지우면 됩니다 — **공개 repo에서는 절대 하지 마세요.**

## 🧩 OKF v0.1 호환

이 브레인은 Google Cloud **Open Knowledge Format (OKF) v0.1**(Apache 2.0 — Andrej Karpathy의 LLM-wiki 패턴 표준화)과 호환됩니다.
- **번들 루트**: `wiki/` (마크다운 + YAML frontmatter)
- **그래프**: 표준 마크다운 링크 `[표시](상대경로.md)` (`[[wikilink]]` 아님)
- **필수 필드**: `type`(OKF 유일 필수) + 규약상 `title`·`tldr`·`tags`
- **예약 파일**: `log.md`(변경 이력). 런타임 목차는 MCP `brain_overview`가 대신함
- **소스 레이어**: `raw/`는 불변 원본(번들 그래프에는 미포함, 2층 출처의 1차 근거)

## ⚙️ 요구사항

- **Python 3** (맥 기본 포함). 외부 패키지·빌드 단계 없음.
- (선택) AI 질의응답: [Claude CLI](https://claude.ai/install.sh) 로그인 — 없으면 챗봇은 키워드 검색으로 폴백.

## 📄 라이선스

[MIT](LICENSE) — 코드는 자유롭게. 단, **당신의 대화 데이터는 당신 것**이며 이 라이선스와 무관합니다.
