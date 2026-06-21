# Love Second Brain — 시각화 대시보드

`raw/`(불변 원본: 카카오톡 대화) + `wiki/`(정제 노드) 마크다운 브레인를 종합해 보여주는 로컬 웹앱.
의존성 없음 — **Python 3 표준 라이브러리만** 사용.

> 시각화(그래프·탐색기·통계·원본)에 더해 **AI 질의응답(RAG)도 이 대시보드가 직접 합니다** —
> 챗봇이 내부적으로 `claude -p`(구독 인증)를 호출해 brain 근거 기반으로 답합니다(claude CLI 없으면 키워드 검색 폴백).
> **읽기/질문 전용** — 노드 수정·생성 기능은 없습니다(그건 repo를 Claude로 열어 MCP·distill로). 서버는 127.0.0.1 로컬 전용 바인딩.

## 실행

```bash
cd love-second-brain
python3 app/server.py          # → http://localhost:8080
PORT=8090 python3 app/server.py   # 다른 포트
python3 app/server.py 8090        # 인자로도 지정 가능
```

## 화면 (탭)

| 탭 | 내용 |
|---|---|
| **대시보드** | 카톡 통계(총 메시지·누가 더 많이 보냈나·월별/연도별/시간대/요일 분포) + 브레인 통계(노드 타입·도메인·태그·`log.md`) |
| **지식 그래프** | wiki 노드 + 본문 마크다운 링크 엣지를 D3 캔버스로 (타입별 색, 미작성 참조는 stub) |
| **노드 탐색기** | wiki 노드 카드 — 타입 필터 + 검색, 클릭 시 본문·출처·연결 상세 |
| **원본 소스** | `raw/`(카톡 월별 원본)를 **카톡 스타일 채팅 버블 UI**로 + 전체 대화 **즉석 grep 검색**(AI 아님, 클릭 시 해당 대화로 점프) |
| **AI 질의응답** | 챗봇에 질문 → `claude -p`로 brain 근거 기반 답변 (claude CLI 없으면 키워드 검색 폴백) |

## 구성

- [`server.py`](server.py) — HTTP 서버. 정적 파일 + 조회 API(`/api/stats` · `/api/chat_stats` · `/api/grep` · `/api/graph` · `/api/nodes` · `/api/raw`) + RAG 챗봇(`POST /api/chat`, `claude -p` 호출). Host 검증 + 127.0.0.1 바인딩으로 로컬 전용.
- [`brain.py`](brain.py) — **공유 데이터 레이어**(frontmatter 파서·노드/그래프 로더·검색). MCP 서버([`../mcp-server/brain_mcp.py`](../mcp-server/brain_mcp.py))도 이 모듈을 import 합니다.
- `index.html` · `app.js` · `index.css` — 프론트엔드.

매 요청마다 `.md`를 다시 읽으므로 **파일 고치고 새로고침만 하면 반영**됩니다(빌드/인덱싱 불필요).
읽기 전용입니다 — 노드 추가/편집은 기존 워크플로(`templates/` 복사 → `wiki/`)를 그대로 쓰세요.
