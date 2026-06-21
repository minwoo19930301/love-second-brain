---
name: distill
description: raw 원본(카카오톡 대화·사진 캡처·구술 메모)을 wiki/ atomic 노드로 정제하는 절차. "정제", "distill", "wiki에 정리", "노드로 만들어", "raw를 위키로" 같은 요청이나, wiki 노드를 새로 만들거나 일괄 생성/갱신할 때 사용.
---

# distill — raw → wiki 정제 절차

이 스킬은 **얇은 래퍼**다. 노드 작성 규약의 source of truth는
[`schema.md`](../../../schema.md) · [`templates/`](../../../templates/) · [`CONTRIBUTING.md`](../../../CONTRIBUTING.md)이며,
이 스킬은 그 규약을 **읽고 따르게 하는 절차**와 distill에만 적용되는 **강화 규칙**만 소유한다.
규칙 본문을 여기에 복붙하지 말 것 — 규약이 바뀌면 SoT만 고치면 된다.

## 절차 (7단계 — 순서대로, 생략 금지)

### 1. 원본 확보
- 대상 자료가 `raw/`에 없으면 `raw/<도메인>/`에 **불변 원본**으로 먼저 저장한다 (수정 금지).
- 카톡 대화는 [`scripts/parse_kakao.py`](../../../scripts/parse_kakao.py)로 `raw/chat/YYYY/YYYY-MM.md`에 적재돼 있다 — 이미 raw에 있으므로 5단계 `sources`에 해당 월 파일 경로를 인용한다.

### 2. 중복 검색
- `search_brain`(MCP 도구) 또는 `app/brain.py`의 `search()`로 기존 노드를 먼저 찾는다.
- **다각도로 검색한다 — 한 번의 질의로 끝내지 말 것:**
  1. 한국어 키워드·영어 키워드로 **각각** 검색 (예: "음식 취향" 과 "food preference")
  2. 만들려는 노드의 **예상 slug를 직접** 검색 (예: `partner-food-preference`)
  3. `list_nodes`(MCP 도구)의 `tag` 필터로 같은 `domain/`·`topic/` 태그의 기존 노드 목록 확인
- MCP를 못 쓰는 환경이면 repo 루트에서 폴백 실행 — 반환형은 `(wiki_hits, raw_hits)` 튜플
  (`wiki_hits = [(score, node)]`, `raw_hits = [(score, doc, text)]`):
  ```bash
  python3 -c "import sys; sys.path.insert(0, 'app'); import brain; w, r = brain.search('음식 취향'); print([n['path'] for _, n in w]); print([d['path'] for _, d, _ in r])"
  ```
- 같은 주제 노드가 이미 있으면 **신규 생성 대신 기존 노드를 갱신**한다 (`updated` 갱신 포함).

### 3. SoT 로드
- [`schema.md`](../../../schema.md)를 읽는다 (노드 타입 6종·엣지 4종·frontmatter 규약).
- `claim`/`concept`/`decision`/`person`/`event`는 [`templates/`](../../../templates/)의 해당 템플릿을 복사해서 시작한다.
  - 주의: decision 템플릿의 placeholder(`[근거 노트](근거-노트.md)`·`[반대 근거](반대-근거.md)`)를 그대로 두면 dangling으로 **lint 실패** — 실제 노드 링크로 교체하거나 해당 행을 삭제할 것.
- `source`는 템플릿이 없다 → schema.md의 frontmatter 규약을 직접 준수한다.

### 4. atomic 분해
- 원본을 **자기완결 단위 노드 N개**로 분해한다. 노드당 `type` 1개.
- 한 노드 = 한 주장. 길어지면 쪼갠다 (CONTRIBUTING.md 팁 동일).

### 5. 작성 (distill 강화 규칙)
schema.md 필수(`type`/`tldr`/`tags`)에 더해, distill 산출물은 아래가 **의무**다:
- **배치 기준** — 신규 노드는 기존 `wiki/<도메인>/` 폴더 우선으로 배정하고, 도메인 폴더 신설은 PR에서 제안한다.
- **`sources` 의무** — raw 경로 또는 외부 위치(아래 표) 인용. 출처 없는 노드 금지.
- **`tldr` = 검색 표면** — 한/영 키워드 병기 (검색이 KO/EN 키워드 스코어링이므로).
  한/영 병기 여부는 자동판정 불가라 **lint가 아닌 PR 리뷰에서 확인**한다.
- **마크다운 링크 ≥ 1** — 기존 노드 또는 이번 배치의 다른 노드로 `[표시](경로.md)` 연결 (lint가 0개를 위반으로 잡는다).
- **decision 노드** — 근거 링크 **≥ 1 의무**(lint 강제). 그 근거를 `## 근거`에 `- supports: [표시](slug.md)` 표준 문법으로 명시하면 **권장**(그래프 관계가 타입드로 잡힘)이나, lint는 형식을 강제하지 않는다 — schema.md §엣지 "관계 표기는 권장"과 정합. `contradicts`는 반대 증거가 실존할 때만 단다 (형식적으로 채우지 말 것).
- **`verified` 검증 등급 — lint엔 선택이지만 distill 산출물엔 항상 단다** (schema.md "검증 등급" 표). lint는 verified가 **없어도 통과**시킨다(optional). 그래서 등급을 항상 붙이는 책임은 distill 절차에 있다 — 아무도 안 달면 신호가 흐려지기 때문. 노드 성격에서 **등급을 자동 제안**하고, 정직하게 매긴다:
  - "코드가 이렇게 **동작한다**"(코드/원본 대조로 만든 기계적 사실) = `code-verified` 후보.
  - "이건 **버그다/의도다/정책상 맞다**"(해석·추정) = **`provisional`** (전문가 확인 전엔 절대 단정 금지). 확인되면 `domain-expert-verified` + `verified_by`.
  - 애매하거나 단순 캡처면 `unverified-capture`. **미검증을 검증된 것처럼 올리지 말 것** — lint 통과는 형식 충족이지 사실 보증이 아니다.
  - ⚠️ **`provisional` 노드는 본문도 추정형으로 쓴다** — tldr·본문을 단정문으로 쓰면 등급 ⚠를 놓친 독자에게 사실처럼 읽힌다. "~로 보인다 / 추정 / 확인 대기"를 명시하고, 보존 가치가 낮으면 노드화 대신 risk-register 한 줄로 남길지 저울질한다.
  - lint는 **있을 때** 값이 유효 enum인지, expert-verified면 verified_by가 있는지(주석만 있는 값은 불인정)만 본다. 어느 등급이 맞는지는 **PR 리뷰**에서 판단.

### 6. lint
```bash
python3 scripts/distill_lint.py <생성/수정한 노드 경로...>
```
- **exit 0 필수.** 위반이 나오면 노드를 고치고 재실행 — 위반 상태로 다음 단계 진행 금지.

### 7. 마무리
- [`log.md`](../../../log.md)에 한 줄 append — 기존 규약 `## [YYYY-MM-DD] action | 제목` (action: ingest/update/distill/fix — log.md 실사용 어휘).

## 원본 유형별 분기 (acquisition + sources 표기만 다름)

분해(4)·lint(6)·log(7)은 모든 유형 공통. 아래는 1단계 확보 방법과 5단계 `sources` 표기만 분기한다.

| 원본 유형 | 확보 (1단계) | sources 표기 (5단계) |
|-----------|-------------|---------------------|
| 카카오톡 대화 | `parse_kakao.py`로 `raw/chat/YYYY/`에 적재(이미 raw에 있음) | `{platform: kakao, url: "../../raw/chat/YYYY/YYYY-MM.md", date: "YYYY-MM-DD"}` (그 발언이 있던 날짜) |
| 사진·캡처 | 텍스트 설명을 `raw/<도메인>/`에 저장하거나 본문에 맥락 기술 | `{platform: photo, url: "<설명/위치>", date: "YYYY-MM-DD"}` |
| 직접 구술/메모 | 전문을 `raw/<도메인>/`에 그대로 저장 | `{platform: raw, url: "../../raw/<도메인>/<파일>.md", date: "YYYY-MM-DD"}` |
