# Love Second Brain — Claude 안내

이 repo는 연인·부부의 카카오톡 대화에서 정제한 지식 브레인입니다. **질의응답(RAG)은 Claude 앱이 직접 합니다** —
이 폴더를 Claude 앱으로 열면 repo 루트의 [`.mcp.json`](.mcp.json)을 통해 **`love-brain` MCP 서버**가
자동 연결되고, Claude가 그 도구로 브레인을 검색·인용해 답합니다. **별도 CLI 설치·로그인·API key가 필요 없습니다.**

> 처음이라면 데이터부터 채워야 합니다 — 카톡 export → `scripts/parse_kakao.py`로 적재 → `wiki/`로 정제.
> 전체 부트스트랩 흐름은 [`README.md`](README.md), 적재·정제 규약은 [`AGENTS.md`](AGENTS.md)·[`schema.md`](schema.md).

## 온보딩 (clone → 열기 → 채우기 → 질문)

```bash
git clone <이 repo>
cd love-second-brain
```
1. **Claude 앱에서 이 폴더를 엽니다.**
2. `love-brain` MCP 서버 연결을 **승인**합니다(최초 1회). — 필요 도구: `python3`(맥 기본 포함).
3. 데이터를 채웁니다([`README.md`](README.md) 참고): 카톡 export → `parse_kakao.py` 적재 → `wiki/` 정제.
4. 이제 그냥 물어보세요. 예:
   - "우리 처음 사귀기 시작한 날이랑 그때 얘기?"
   - "상대가 좋아하는 음식이랑 싫어하는 거 정리해줘."
   - "둘만의 별명·은어는 뭐가 있어?"

(선택) 시각화 대시보드: `python3 app/server.py` → http://localhost:8080 (채팅 뷰어·grep 검색·통계·그래프).

## Claude에게: 답변 방식

이 브레인에 대한 질문을 받으면 **추측하지 말고 항상 도구로 근거를 찾아** 답하세요. (둘의 추억이라 정확함이 중요합니다.)

1. 방향이 안 잡히면 **`brain_overview`**로 전체 구조를 먼저 봅니다.
2. **`search_brain(query)`**로 관련 wiki 노드·raw 대화 원본을 찾습니다.
3. 필요한 문서는 **`read_doc(path)`**로 전문을 확인합니다. 그래프 탐색은 **`get_node(slug)`**(연결된 마크다운 링크 따라가기).
4. 답변에는 **근거 경로를 `path` 형태로 인용**합니다. 브레인에 없으면 "아직 정리돼 있지 않다"고 솔직히 말합니다.
   - **`verified` 등급을 존중하세요.** 노드/검색결과의 `⚠`(provisional·unverified-capture·확인자 없는 사람)는 대화 한 토막만 보고 만든 미검증 추정일 수 있습니다 — 사실로 단정하지 말고 "대화상으로는 …인 듯" 식으로 밝혀 인용합니다. **등급 미표기(빈값)는 ⚠가 아니라 중립**입니다.
5. 새 지식을 정리해 달라는 요청이면 [`templates/`](templates/)를 복사해 `wiki/<도메인>/`에 노드로 추가하고
   [`log.md`](log.md)에 한 줄 append 합니다. 규약은 [`schema.md`](schema.md).
   wiki 노드 생성/정제 시에는 [`.claude/skills/distill`](.claude/skills/distill/SKILL.md) 절차를 따르고 `python3 scripts/distill_lint.py <노드 경로...>`를 통과시킵니다.

## 구조 (요약)

- `raw/<도메인>/` — **불변 원본**(카톡 월별 대화 `raw/chat/YYYY/`). 수정 금지, source of truth.
- `wiki/<도메인>/` — **정제 노드**(claim·concept·decision·source·person·event). frontmatter `type`/`tldr`/`tags`/`sources`, 본문 마크다운 링크 `[표시](경로.md)`로 관계.
- 도메인: `person · love · taste · events · marriage · rules · lexicon · life`.
- 흐름: `raw(원본) → distill(정제) → wiki(노드) → query(질의)`.
- 더 보기: [`README.md`](README.md) · [`schema.md`](schema.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) · 카톡 적재는 [`AGENTS.md`](AGENTS.md).

## MCP 서버

- 실체: [`mcp-server/brain_mcp.py`](mcp-server/brain_mcp.py) — 순수 Python(표준라이브러리만), 도구: `search_brain`·`read_doc`·`list_nodes`·`get_node`·`brain_overview`.
- 브레인 변경을 **mtime으로 자동 감지해 바뀐 파일만 재파싱**합니다 — 파일을 고치면 바로 반영(빌드·인덱스 재생성 불필요, 캐시는 프로세스 메모리 전용).
