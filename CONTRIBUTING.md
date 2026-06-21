# 노트 추가하는 법

**4단계면 끝:**
1. `templates/`에서 타입 골라 복사 → `wiki/<도메인>/<슬러그>.md`
2. frontmatter 채우기 — `type`, `title`, `tldr`, `tags` (출처 있으면 `sources`, 신뢰 등급은 `verified` 권장)
   - `verified`는 **선택**이지만 달아두면 좋다(lint는 있을 때만 enum 검사, 없으면 통과). 정직하게: 대화 원문 대조면 `code-verified`, 취향·감정 추정이면 `provisional`, 애매하면 `unverified-capture`. 본인이 확인했을 때만 `domain-expert-verified`(+`verified_by`). 자세히는 [`schema.md`](schema.md)의 검증 등급.
3. 본문 작성. 관련 노트는 마크다운 링크 `[표시](상대경로.md)`로 연결.
4. 커밋 (또는 PR). 끝.
   - 단, **정제(distill) 일괄 산출물**(여러 노드 동시 생성/갱신)은 **`python3 scripts/distill_lint.py <생성/수정한 노드 경로...>` 통과(exit 0) 의무**. (경로 인자 없이 실행하면 wiki/ 전체를 스캔하므로 반드시 본인이 만든/고친 노드 경로만 넘길 것)

## 팁
- **원본 자료**(카톡 대화 export)는 [`scripts/parse_kakao.py`](scripts/parse_kakao.py)로 `raw/chat/`에 *그대로* 적재.
- **완벽하게 안 써도 됨** — 일단 올리면 LLM이 정리·연결·중복제거.
- 한 노트 = 한 주장(claim) 지향. 길어지면 쪼개기.
- 자세한 규약 → [`schema.md`](schema.md)

> 목표: 사람은 *소싱·판단*, 무거운 유지보수(엣지·stale·인덱스)는 도구가.

## ⚠️ 프라이버시

이 repo가 **공개(public)** 라면 **개인 대화 데이터(`raw/chat/**`, `wiki/**/*.md`, 카톡 원문 `.txt`)를 커밋하지 마세요.** [`.gitignore`](.gitignore)가 기본으로 막아 둡니다. 데이터까지 백업하려면 **private repo**를 쓰세요.
