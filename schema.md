# Knowledge Schema

second brain 노트 작성 규약 (**최소 스키마** — 필요할 때만 확장).

> **OKF v0.1 호환**: 그래프는 표준 마크다운 링크 `[표시](상대경로.md)`, 필수 필드 `type`(+규약 `title`·`tldr`·`tags`), 예약 파일 `log.md`. 번들 루트는 `wiki/`. 자세히는 [README](README.md#-okf-v01-호환).

## 레이어
| 폴더 | 역할 |
|------|------|
| `raw/<domain>/` | 불변 원본 (카톡 월별 대화 등). **수정 금지.** 검증용 source of truth. |
| `wiki/<domain>/` | 정리한 노드 (atomic). LLM/사람이 작성·유지. |
| `templates/` | 노트 템플릿. |

> 도메인 하위 폴더(person/love/taste…)는 *coarse 정리*일 뿐. 진짜 구조는 아래 **노드 type + 엣지 + frontmatter**.

## 도메인 (coarse 분류)
`person`(인물: 나·상대·가족·반려동물) · `love`(애정·로맨스·기념일) · `taste`(취향: 음식·물건·색·브랜드, 선호/비선호) · `events`(데이트·여행·이벤트 추억) · `marriage`(연애→결혼→신혼 마일스톤·웨딩 준비) · `rules`(둘의 규칙·약속·갈등 패턴·화해법) · `lexicon`(은어·별명·말버릇·이모티콘) · `life`(일상·커리어·집안일·돈·건강)

## 노드 타입 (frontmatter `type:`)
- **claim** — 하나의 자기완결 주장 (★ 기본 단위). 예: "상대는 민트초코를 싫어한다"
- **concept** — 개념/용어 정의. 예: 둘만의 은어의 뜻
- **decision** — 함께 내린 결정 (근거 필수). 예: "신혼집은 OO로 정함"
- **source** — 원본 출처 메타 (카톡 대화 구간 등)
- **person** — 인물 (나·상대·가족·반려동물)
- **event** — 사건·추억 (날짜 있는 일). 예: 첫 데이트, 프로포즈, 신혼여행

## 엣지 타입 (본문 마크다운 링크 `[표시](상대경로.md)`로 연결; 관계 표기는 권장)
- **supports** — 근거가 됨
- **contradicts** — 반박/모순
- **extends** — 확장/기반
- **similar** — 유사

## frontmatter
```yaml
type: claim            # 필수
title: "노드 제목"      # 필수 (OKF 표준 쿼리 필드)
tldr: "한 줄 요약"      # 필수
tags: [domain/taste, topic/food]   # 필수 (namespace: domain/ topic/ person/)
sources:               # 권장 (출처 있는 주장은 필수)
  - {platform: kakao, url: "../../raw/chat/2021/2021-03.md", date: "2021-03-14"}
verified:              # 선택 — 비우면 중립. 달면 아래 표의 enum. distill 산출물엔 항상 단다
verified_by:           # verified가 domain-expert-verified면 필수 (확인한 사람: 본인/상대)
created: 2026-01-01
updated: 2026-01-01
```

## 검증 등급 (`verified:`) — 선택(있으면 enum 준수)

> **왜 필요한가:** 이 스키마(sources·링크·atomic)는 **형식**을 강제할 뿐
> 주장의 **진실성을 보증하지 못한다.** lint를 통과한 노드도 "잘 구조화됐고 출처가 달림"이지
> "맞다"가 아니다. 특히 카톡 한 토막만 보고 만든 노드는 *그 순간의 농담·맥락*을
> 사실로 오독할 수 있다. `verified`는 그 신뢰 차원을 노드에 **명시**해, 읽는 사람·RAG가 가중치를 두게 한다.

| 값 | 의미 | 안전하게 캡처? | 추가 의무 |
|----|------|:---:|----|
| (빈값) | 등급 미부여 — **중립**(⚠ 없음). 템플릿 기본값 | — | — |
| `unverified-capture` | 대화에서 초기 캡처. 아직 본인 확인 안 됨 (명시적 미검증 → ⚠) | — | — |
| `code-verified` | 대화 원문 대조로 검증된 **사실** (날짜·발언 등, 반증가능) | ✅ | — |
| `domain-expert-verified` | 본인(나/상대)이 **맞다고 확인**함 | ✅ | `verified_by` (확인한 사람) |
| `provisional` | **해석성 주장**(취향·의도·감정 추정). 본인 확인 대기 | ⚠️ | — |

**구분 기준:** "이 날 이런 대화를 **했다**"는 `code-verified`로 충분하다(원문 대조 가능).
"상대가 이걸 **진짜 좋아한다/싫어한다**"는 해석이므로 본인 확인 전엔 **`provisional`**,
확인 후 `domain-expert-verified`(+`verified_by`)로 승격한다.
(lint는 **있을 때** 값이 유효한지만 검사하고 없으면 통과시킨다. distill 절차가 산출물에 등급을 항상 달아 신호가 흐려지지 않게 한다.)

## 규칙 (4개만)
1. **claim은 자기완결** — 본문 없이 한 줄(tldr)만 봐도 이해되게.
2. **출처 있는 주장엔 sources** — 카톡 근거면 `raw/chat/...` 경로. 없으면 본문에 `TODO: source`.
3. **검증 등급을 정직하게** — 모르면 `unverified-capture`/`provisional`로 둘 것. 농담을 사실처럼 올리지 않는다. (lint 통과 ≠ 사실)
4. **무거운 건 도구가 한다** — 엣지 정합성·stale 관리는 LLM이 유지. 사람은 위 최소만.
