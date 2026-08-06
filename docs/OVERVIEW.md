# coding-agent — 하네스 엔지니어링 기반 자율 개발 에이전트

> 이 문서는 `coding-agent`가 현재 시스템에서 어떤 역할을 하는지, 그리고 `stablenet-knowledge`·`Claude Code`와
> 어떻게 맞물려 동작하는지를 그림 중심으로 빠르게 이해하기 위한 개요 문서다.
> 상세 빌드/설정은 [SETUP.md](SETUP.md), 굵직한 설계 근거는 [adr/](adr/)(특히 ADR-0006·ADR-0007),
> 자잘한 결정들은 아래 §8을 참고.

---

## 1. 한 문장 정의

> **coding-agent**는 **하네스 엔지니어링(harness engineering)** 위에서, **stablenet-knowledge를 통한 Retrieval(RAG)** 로
> 코드베이스를 근거 있게 이해하고, **유저의 요구사항(Jira 티켓 등)을 분석 → 설계 → 코드 구현 → 테스트 → PR**
> 까지 자율적으로 수행하는 다중 에이전트다.

여기서 "하네스 엔지니어링"이란 — LLM 하나에게 통째로 맡기지 않고, **상태 머신 + 격리된 에이전트 +
파일 산출물 + 외부 결정론 백엔드**로 작업을 구조화해서, 멈춰도 이어지고(resumable) 추측 대신
근거로 판단하게 만든 골격을 말한다.

---

## 2. 큰 그림 — coding-agent · stablenet-knowledge · Claude Code의 관계

가장 먼저 잡아야 할 멘탈 모델: **누가 누구를 품고 있는가.**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Claude Code  (런타임 / 호스트)                                                  │
│  · LLM(Opus/Sonnet)을 구동하는 CLI·앱                                            │
│  · 플러그인 자동 발견, 슬래시 커맨드, 에이전트, 스킬, 훅, MCP 클라이언트를 제공      │
│                                                                                │
│   ┌────────────────────────────────────────────────────────────────────────┐ │
│   │  coding-agent  (Claude Code 플러그인 = "하네스")                           │ │
│   │  · /work /analyze /review /merge /status /bench  슬래시 커맨드             │ │
│   │  · orchestrator / planner / implementer / evaluator  4개 에이전트         │ │
│   │  · state.json + *.md 산출물로 된 문서 기반 상태 머신                        │ │
│   │                                                                          │ │
│   │        planner 가 검색을 위해 호출 ──┐                                     │ │
│   └──────────────────────────────────────┼───────────────────────────────────┘ │
│                                          │ (MCP 프로토콜)                        │
│         Claude Code의 MCP 클라이언트가 중개 │                                       │
│   ┌──────────────────┬───────────────────┼──────────────────┐                  │
│   ▼                  ▼                    ▼                  ▼                  │
│ ┌────────────┐  ┌──────────┐      ┌──────────────┐                            │
│ │ atlassian  │  │   stablenet-knowledge    │      │  chainbench  │   ← MCP 3종(atlassian=외부) │
│ │ (in-tree)  │  │ (외부)   │      │   (외부)      │                            │
│ └────────────┘  └────┬─────┘      └──────────────┘                            │
└─────────────────────┼──────────────────────────────────────────────────────┘
                      │  stablenet-knowledge 내부 (별도 프로세스/저장소, LLM 호출 0 = 결정론)
                      ▼
            ┌───────────────────────────────────┐
            │  stablenet-knowledge = code-knowledge-system       │
            │   ┌─────────┐   ┌─────────┐        │
            │   │   ckv   │ + │   ckg   │        │  in-process로 합성
            │   │ 의미검색  │   │ 코드그래프 │       │
            │   │ (RAG)   │   │(graph-RAG)│      │
            │   └────┬────┘   └─────────┘        │
            │        │ bge-m3 임베딩 (Ollama)      │
            └────────┴──────────────────────────┘
```

**같은 관계를 Mermaid로:**

```mermaid
flowchart TB
    subgraph CC["Claude Code · 런타임/호스트 (LLM 구동 + 플러그인/MCP 호스팅)"]
        direction TB
        subgraph CA["coding-agent · 플러그인 = 하네스"]
            direction TB
            ORCH["orchestrator<br/>(전체 흐름 디스패치)"]
            PLAN["planner<br/>(분석 + 설계)"]
            IMPL["implementer<br/>(구현)"]
            EVAL["evaluator<br/>(테스트)"]
            ORCH --> PLAN --> IMPL --> EVAL
        end
        MCPC["Claude Code MCP 클라이언트"]
        CA -.->|MCP 프로토콜| MCPC
    end

    JG["Atlassian MCP<br/>(외부 공식 플러그인 · OAuth)"]
    stablenet-knowledge["stablenet-knowledge MCP<br/>(외부 · 코드 이해)"]
    CB["chainbench MCP<br/>(외부 · 출력 검증)"]

    MCPC --> JG
    MCPC --> stablenet-knowledge
    MCPC --> CB

    subgraph CKSI["stablenet-knowledge = code-knowledge-system (별도 프로세스 · LLM 호출 0)"]
        direction LR
        CKV["ckv<br/>의미검색 (RAG)"]
        CKG["ckg<br/>코드그래프 (graph-RAG)"]
        CKV ---|in-process 합성| CKG
    end
    stablenet-knowledge --> CKSI
    CKV -.->|bge-m3 임베딩| OLLAMA["Ollama"]

    PLAN -.->|"검색 호출 (유일한 stablenet-knowledge 소비자)"| MCPC
```

**세 줄 요약**

- **Claude Code** = 무대(런타임). LLM을 돌리고 플러그인/MCP를 호스팅한다.
- **coding-agent** = 그 무대 위에서 도는 **플러그인이자 하네스**. 일을 단계로 쪼개고 에이전트에게 나눠준다.
- **stablenet-knowledge** = coding-agent가 **MCP로 호출하는 외부 검색 두뇌**. 코드베이스를 RAG로 이해하게 해준다.

> 관계의 핵심: coding-agent는 stablenet-knowledge를 *포함*하지 않는다. stablenet-knowledge는 **별도 저장소·별도 프로세스**이고,
> Claude Code의 MCP 클라이언트를 통해 **호출**될 뿐이다. 그래서 stablenet-knowledge가 죽거나 degraded여도
> coding-agent는 멈추지 않는다(검색 품질만 낮아진다).

---

## 3. 동작 흐름 — 요구사항이 PR이 되기까지

```
                              ┌─────────────────────────────────────────────┐
   유저 요구사항               │              coding-agent (하네스)             │
  ┌──────────────┐            │                                               │
  │  Jira 티켓    │  inbound   │   ┌─────────────┐                            │
  │  STABLE-1234 │──필터링────▶│   │ orchestrator│ ◀── 전체 흐름을 보는 유일한 두뇌 │
  │  (또는 자유    │  (시크릿     │   └──────┬──────┘                            │
  │   텍스트)     │   차단)     │          │ 상태 전이로 에이전트 디스패치          │
  └──────────────┘            │          ▼                                    │
        ▲                     │  ┌───────────────────────────────────────┐   │
        │ Atlassian MCP(외부) │  │ ANALYSIS → PLANNING → DESIGN           │   │
        │ (민감정보가 LLM에    │  │   ▲ planner (요구사항 분석 + 설계)       │   │
        │  닿기 전에 차단)     │  │   │                                     │   │
        │                     │  │   │  ┌──────────┐                       │   │
        │                     │  │   └──│  stablenet-knowledge MCP  │◀── Retrieval (RAG)    │   │
        │                     │  │      │ (검색두뇌) │   의미검색 + 그래프검색  │   │
        │                     │  │      └──────────┘                       │   │
        │                     │  │            ▲                            │   │
        │                     │  │            │ "이 코드 어디서 호출돼?       │   │
        │                     │  │            │  뭘 깨뜨려? 동시성 위험은?"     │   │
        │                     │  │  IMPLEMENTATION  (implementer: step당 1커밋)│   │
        │                     │  │       │                                 │   │
        │                     │  │       ▼                                 │   │
        │                     │  │  EVALUATION  (evaluator: 4단계 게이트)    │   │
        │                     │  │       │   unit+race · lint · security ·  │  │
        │                     │  │       │   chainbench(통합) ◀─ chainbench MCP │
        │                     │  │       ▼                                 │   │
        │                     │  │   PASS ─────────────▶ PR 생성 + Jira 갱신 │  │
        │                     │  │   FAIL ─▶ bugfix 사이클(≤3) 또는 BLOCKED  │   │
        │                     │  └───────────────────────────────────────┘   │
        │                     │                                               │
        └─────────────────────│──── outbound 텍스트(PR/커밋/댓글)             │
              pr-sanitize로     │      → pr-sanitize 스크럽 후 외부로           │
              outbound도 차단    └─────────────────────────────────────────────┘
                                                       │
                                                       ▼
                                              ┌──────────────┐
                                              │  GitHub PR   │
                                              └──────────────┘
```

**같은 흐름을 Mermaid로:**

```mermaid
flowchart TD
    REQ["유저 요구사항<br/>Jira 티켓 / 자유 텍스트"]
    REQ -->|"Atlassian MCP(외부): 인바운드 필터 없음"| INTAKE["TICKET_INTAKE"]
    INTAKE --> ANALYSIS["ANALYSIS"]
    ANALYSIS --> PLANNING["PLANNING"]
    PLANNING --> DESIGN["DESIGN"]

    stablenet-knowledge["stablenet-knowledge (RAG + graph-RAG)"]
    ANALYSIS <-->|검색| stablenet-knowledge
    PLANNING <-->|검색| stablenet-knowledge
    DESIGN <-->|검색| stablenet-knowledge

    DESIGN --> IMPL["IMPLEMENTATION<br/>(step당 1커밋)"]
    IMPL --> EVALN["EVALUATION<br/>4단계 게이트"]
    EVALN <-->|통합 테스트| CB["chainbench"]

    EVALN -->|PASS| DONE["PR 생성 + Jira 갱신"]
    EVALN -->|FAIL| FIX{"bugfix 사이클<br/>≤ 3회"}
    FIX -->|재시도| PLANNING
    FIX -->|한계 초과| BLOCKED["BLOCKED"]

    DONE -->|"pr-sanitize: outbound 스크럽"| PR["GitHub PR"]
```

---

## 4. 두 개의 기둥

### 기둥 A — 하네스: "문서 기반 상태 머신"

LLM의 컨텍스트는 언제든 잘릴 수 있다. 그래서 **모든 단계가 산출물을 디스크에 남긴다.**

```
  ANALYSIS  ──▶  analysis.md      ┐
  PLANNING  ──▶  plan.md          │  세션이 끊겨도
  DESIGN    ──▶  design-v{N}.md   ├─ 파일에서 정확히
  EVALUATION──▶  test-report.md   │  이어받음 (resumable)
  (전 단계) ──▶  state.json       ┘
```

그리고 일을 **4개의 격리된 에이전트**로 나눈다 — 각자 자기 컨텍스트만 보고, orchestrator만 전체를 본다.

| 에이전트 | 하는 일 |
|---|---|
| **orchestrator** | 상태 전이 디스패치, MCP pre-flight, PR/Jira 완료, 버그 사이클 재진입 |
| **planner** | 요구사항 **분석 + 설계** — stablenet-knowledge를 쓰는 유일한 에이전트 |
| **implementer** | 코드 **구현** (원자 step당 1커밋) |
| **evaluator** | **테스트** (4단계 검증 게이트) |

### 기둥 B — Retrieval: "stablenet-knowledge를 통한 RAG"

planner는 낯선 거대 코드베이스(`go-stablenet`)를 **추측하지 않는다.** 대신 stablenet-knowledge에 물어봐서
**실제 코드에 근거**한 설계를 한다.

```
   planner의 질문                stablenet-knowledge (RAG 엔진)              근거 있는 답
  ─────────────────         ┌───────────────────┐       ─────────────────
  "이 요구사항과 관련된  ──▶  │ ① 의미 검색 (RAG)  │  ──▶   관련 함수/파일 목록
   코드가 어디지?"            │   bge-m3 임베딩     │
                            │                    │
  "이 함수 고치면     ──▶   │ ② 그래프 검색       │  ──▶   호출자/피호출자 그래프,
   뭐가 깨지지?"             │   (graph-RAG)      │        영향 범위, 동시성 위험
                            │   호출그래프·영향분석 │
                            └───────────────────┘
```

이게 바로 일반 RAG와 같은 원리다 — **검색으로 가져온 근거를 컨텍스트에 넣어 LLM이 환각 없이 판단**하게
만드는 것. 다만 텍스트 의미검색(RAG)에 더해 **코드 호출 그래프(graph-RAG)** 까지 합성한다는 점이 특징이다.

---

## 5. MCP 3종 — 에이전트의 손과 발

coding-agent가 외부와 상호작용하는 통로는 (Claude Code의 MCP 클라이언트를 거치는) MCP 서버 3개이고,
역할이 깔끔하게 나뉜다.

```
   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
   │  atlassian(외부)│   │      stablenet-knowledge       │   │   chainbench   │
   │   (입력 보안)   │   │  (코드 이해)    │   │   (출력 검증)   │
   ├────────────────┤   ├────────────────┤   ├────────────────┤
   │ Jira 내용을     │   │ RAG + graph-RAG │   │ 실제 체인 띄워  │
   │ 가져오되 시크릿  │   │ 으로 코드 검색   │   │ tx/계약 보내고  │
   │ 을 LLM 전에     │   │ (planner 전용)  │   │ 합의 검증       │
   │ REDACT/BLOCK    │   │                 │   │ (evaluator 게이트)│
   └────────────────┘   └────────────────┘   └────────────────┘
      이 저장소 in-tree      외부 sibling repo     외부 sibling repo
         (Go)               (bge-m3 임베딩)        (TS+Go)
```

**같은 역할 분담을 Mermaid로:**

```mermaid
flowchart LR
    AG["coding-agent<br/>에이전트들"]

    subgraph IN["입력 보안"]
        JG["Atlassian MCP (외부 플러그인)<br/>OAuth · 인바운드 필터 없음"]
    end
    subgraph UNDERSTAND["코드 이해"]
        stablenet-knowledge["stablenet-knowledge (외부)<br/>RAG + graph-RAG<br/>planner 전용"]
    end
    subgraph VERIFY["출력 검증"]
        CB["chainbench (외부, TS+Go)<br/>실제 체인 tx/계약 + 합의 검증"]
    end

    JG -->|정제된 텍스트만| AG
    AG <-->|"검색 질의/응답"| stablenet-knowledge
    AG -->|"4단계 게이트"| CB

    AG -->|"PR/커밋/댓글"| SAN["pr-sanitize<br/>(outbound 스크럽)"]
    SAN --> EXT["GitHub / Jira"]
```

> **설계 원칙 — Binary = deterministic, Session = LLM**
> 외부 백엔드(stablenet-knowledge·chainbench) 바이너리는 LLM 호출이 **0**이다. 임베딩·그래프·테스트 실행 같은
> **결정론적 작업만** 담당하고, 모든 *판단(LLM)* 은 coding-agent 세션 레이어에 모인다.
> 그래서 같은 입력이면 백엔드는 항상 같은 결과를 준다.

> **보안은 양방향 대칭**
> 입력 필터는 없다 — `jira-gateway` 폐기와 함께 감수한 손실이다(ADR-0013 §2.3). 출력만 막는다:
> 출력(PR 본문·커밋·Jira 댓글)은 `pr-sanitize`가 같은 패턴으로 스크럽한 뒤 내보낸다.

에이전트가 쓸 수 있는 도구 표면(이 리포 소유 41개 — stablenet-knowledge 15 + chainbench 26; Atlassian은 외부라 계약 대상 아님)은
[`scripts/contract/agent-mcp.schema.json`](../scripts/contract/agent-mcp.schema.json)에
고정(SSoT)되고, [`scripts/contract/lint-tool-names.sh`](../scripts/contract/lint-tool-names.sh)로 drift를 검출한다.

---

## 6. 진입점 (슬래시 커맨드)

| 명령 | 의미 |
|---|---|
| `/core-dev:work STABLE-1234` | 메인. 요구사항 → PR 풀 사이클 (`--local`로 Jira 없이도 가능) |
| `/core-dev:analyze "..."` | 자유 텍스트 요구사항으로 시작 (Jira 불필요) |
| `/core-dev:review <PR>` | PR 리뷰 코멘트를 받아 bugfix 사이클 재진입 |
| `/core-dev:merge` | **main을 건드리는 유일한 명령** — 승인+green일 때만 squash merge |
| `/core-dev:status` | 진행 상황 조회 |
| `/core-dev:bench` | A(stablenet-knowledge)/B(code-only)/C(code+skills) 3-way 정보 regime 비교 harness |

---

## 7. 핵심을 한 번 더

```
  ┌─ 하네스 엔지니어링 ─┐   상태 머신 + 격리 에이전트 + 파일 산출물 → 멈춰도 이어짐
  │                    │
  │  coding-agent      │   ┌─ stablenet-knowledge Retrieval (RAG) ─┐   추측 대신 실제 코드 근거로 설계
  │   (Claude Code      │   │                        │
  │    플러그인)        │   └─ 요구사항(Jira) 분석 ──┘ → 설계 → 구현 → 테스트 → PR
  └────────────────────┘                                              (자율 수행)
```

요구사항 한 줄을 넣으면, 검색으로 코드를 이해하고, 설계 문서를 쓰고, 커밋 단위로 구현하고,
4단계로 검증한 뒤, 리뷰된 PR로 돌려주는 — **"읽고 추측하는 AI"가 아니라 "근거를 검색해 일하는
엔지니어링된 에이전트"** 다.

- **Claude Code**가 무대를 깔고,
- **coding-agent**가 그 위에서 일을 구조화하며,
- **stablenet-knowledge**가 그 일에 필요한 코드 근거를 RAG로 공급한다.

---

## 8. 설계 결정 로그 (자잘한 결정들의 Why)

> §1~§7이 지금의 아키텍처를 설명한다면, 이 표는 "왜 다른 대안이 아니라 이거였나"를 압축 보존한다.
> 굵직한 두 결정(Proxy MCP Gateway 보안 모델, B+C 하이브리드 아키텍처)은 각각
> [ADR-0006](adr/ADR-0006-proxy-mcp-gateway-security-model.md) · [ADR-0007](adr/ADR-0007-bc-hybrid-harness-architecture.md)로
> 승격됐다. 아래는 `HANDOFF.md`(2026-06-05 스냅샷, 삭제됨) §5에서 추출한 나머지 결정들.

| 결정 | Why | 위치 |
|------|-----|------|
| ~~**Jira Gateway MCP 언어 = Go**~~ | 처음 TypeScript로 시작 → 다른 TS 사용처가 없어 Go로 전환. **폐기됨(ADR-0013)** — 서버 자체를 공식 Atlassian MCP로 대체 | (삭제됨) |
| **도구 이름 SSoT 스키마 + lint** | stablenet-knowledge의 실제 도구 이름과 agent/command 마크다운의 도구 참조가 따로 드리프트하기 쉬움 → 스키마를 단일 소스로 두고 lint로 기계 검증 | `scripts/contract/agent-mcp.schema.json` + `scripts/contract/lint-tool-names.sh` |
| **자체 stablenet-knowledge-mcp shim 폐기** | 자체 in-tree 구현이 외부 stablenet-knowledge(code-knowledge-system)와 표면(도구 이름·응답 스키마)이 어긋남. 외부가 더 풍부한 도메인 시스템을 제공하므로 in-tree 코드를 통째 삭제하고 외부 바이너리(`${STABLENET_KNOWLEDGE_MCP_BIN}`)에 위임 | `plugins/core-dev/.mcp.json`의 `stablenet-knowledge` 항목 |
| ~~**ADF→Markdown 자체 구현**~~ | **불필요해짐(ADR-0013)** — `getJiraIssue(responseContentFormat:"markdown")`가 서버 쪽에서 변환한다 | (삭제됨) |
| **Jira transition 3-tier lookup** | 워크플로 transition 이름은 프로젝트마다 다르다 → name → status name → statusCategory key 순으로 case-insensitive 매칭해, 별도 설정 파일 없이 프로젝트별 차이를 흡수. 서버가 하던 일을 호출부가 이어받았다(ADR-0013) | `plugins/core-dev/skills/jira-via-atlassian/SKILL.md` §3 |
| **bge-m3 임베딩 (다국어)** | nomic 계열은 영어 전용인데 사용자가 한국어를 쓴다 → 다국어 임베더가 필요. 1024-dim은 bge-large와 동일해 향후 스왑 시 스키마 마이그레이션이 불필요 | `docs/SETUP.md §4.3` |
| **MCP pre-flight 3-layer** | 단일 SessionStart 훅이 없어, 세 지점(orchestrator 초입, work.md의 jira 실패 분기, planner의 stablenet-knowledge 헬스체크)으로 나눠 분담 | `plugins/core-dev/agents/{orchestrator,planner,evaluator}.md` |
| **L3 invariant backstop을 skill로** | Claude Code에 SessionStart 주입 기능이 없어, planner+evaluator에 늘 grant되는 skill로 invariant 요약(~500토큰)을 always-on으로 유지 | `plugins/core-dev/skills/stablenet-invariants/SKILL.md` |
| **stablenet-context를 경량 분류기로 축소** | 정적 컨트랙트 이름(`GovStaking` 등)은 시간이 지나면 drift한다 → path→module 분류만 남기고, 실제 도메인 지식은 stablenet-knowledge 라이브 검색 + invariant backstop에 위임 | `plugins/core-dev/skills/stablenet-context/SKILL.md` |
| **3-way bench가 별도 Python harness** | 결정론적 측정은 Go 에이전트 실행과 분리하는 게 맞다 → `bench/`는 Python으로 A(stablenet-knowledge)/B(code-only)/C(code+skills) 세 정보 regime을 비교 | `bench/compare.py` + `plugins/core-dev/skills/bench-orchestration/SKILL.md`, 상세 정의는 [bench-abc-mode-definitions.md](bench-abc-mode-definitions.md) |
| **transcript-grade observability** | 서브에이전트 prompt/response verbatim이 없으면 토큰/비용을 사후 계산할 수 없다 → 매 에이전트 완료마다 verbatim을 기록해 3-way bench의 measurement substrate로 사용 | `plugins/core-dev/hooks/on-agent-complete.sh` |
| **`/merge` body 2-tier 전략** | step이 10개 이하면 전체 나열, 11개 이상이면 [Interface, Implementation, Tests, Docs, Misc] 5-카테고리로 묶어 PR 본문이 과도하게 길어지지 않게 함 | `plugins/core-dev/commands/merge.md` |
| **race detector 범위 제한** | 전체 코드베이스에 `-race`를 걸면 시간이 폭발적으로 늘어난다 → 그래프 검색으로 동시성 위험이 있는 패키지만 추출해 그쪽만 `-race` 실행 | `plugins/core-dev/agents/evaluator.md` |
| **release 변종의 tag/push는 사용자 확인 게이트** | 자동 태깅·푸시는 되돌리기 어려운 작업 → orchestrator가 사용자 명시 승인 없이는 절대 tag/push하지 않음 | `plugins/core-dev/agents/orchestrator.md` 안전 정책 |
| **`agent-mcp.schema.json`의 `Citation`/`PRRef` 타입 정의 제거(2026-07-21)** | 스키마 어디서도 `$ref`로 참조되지 않는 죽은 정의였다. `Citation`(`{file, start_line, end_line}`)은 stablenet-knowledge 도구가 반환하는 evidence pack의 citation을 타입화하려던 것으로 보이나, 실제로는 `bench/stablenet-knowledge-bench/bench_io/envelope.py`의 `Citation` dataclass(`file, start_line, end_line, symbol` — `symbol` 하나 더 있음)로 스키마와 무관하게 독립 구현돼 있었다. `PRRef`(`{number, title, merged_at}`)는 `cks_context_change_history`의 PR-refs 반환을 타입화하려던 것으로 보이나 대응 구현체가 Python/Go 어디에도 없다. 현재 스키마는 `chainbench_report`를 빼면 모든 도구가 `input`만 정의하고 `output`이 없다 — **나중에 도구 output 타입을 스키마에 추가한다면** 위 `envelope.py`의 4-필드 `Citation`을 기준으로 삼는다(실제 운영 코드가 검증한 shape이므로) | `scripts/contract/agent-mcp.schema.json`, `bench/stablenet-knowledge-bench/bench_io/envelope.py` |
