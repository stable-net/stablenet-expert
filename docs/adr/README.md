# Architecture Decision Records (ADR)

> **Tier 2.** 하나의 결정 = 하나의 ADR. 결정이 바뀌면 **새 ADR**를 만들고 옛 ADR을
> `Superseded by ADR-NNNN`으로 표시한다(삭제하지 않는다).

## 인덱스

| ADR | 제목 | 상태 | 구현 검증 (코드 근거) |
|---|---|---|---|
| [ADR-0001](ADR-0001-domain-pack-contract.md) | Domain-Pack Contract (멀티프로젝트 확장) | Accepted (2026-06-22) | 구현됨 — `plugins/core-dev/domains/go-stablenet/`(domain-pack.json·context.md·invariants.md) 존재 |
| [ADR-0002](ADR-0002-setup-and-doctor.md) | `/coding-agent:setup` 확장 + `/coding-agent:doctor` | Accepted (2026-06-23) | 구현됨 — `plugins/core-dev/commands/{setup,doctor}.md`, PR #22·#23 머지 (v0.1.30) |
| [ADR-0003](ADR-0003-reproduction-and-fix-validity.md) | Reproduction vs Fix-Validity 분리 + 2-티어 재현 | Accepted (2026-06-23) | 구현·머지 — PR #18 (v0.1.25). 라이브 무회귀 잔여(§6) |
| [ADR-0004](ADR-0004-doctor-remediation-routing.md) | doctor→setup remediation routing + single-source fix table | Accepted (2026-06-26) | 구현됨 — PR #31·#33, `plugins/core-dev/scripts/doctor.py` REMEDIATION 테이블 |
| [ADR-0005](ADR-0005-stablenet-expert-marketplace-split.md) | stablenet-expert 마켓플레이스 분리 + core-dev/cq 경계 | Accepted (2026-07-20) | 구현됨 — `stablenet-expert` 리포로 이관 완료(§2.1/2.2/2.4). §2.3(cq 분리)은 재검토 후 철회. §5 dapp 로드맵 제외 반영 (4-카테고리로 축소) |
| [ADR-0006](ADR-0006-proxy-mcp-gateway-security-model.md) | Proxy MCP Gateway 보안 모델 (양방향 민감정보 필터링) | Accepted (historical, 2026-07-21 추출); 인바운드 절만 Partially superseded by ADR-0013 (2026-08-04) | 아웃바운드(`pr-sanitize`)만 유효 — 인바운드 구현체(`packages/jira-gateway-mcp/internal/filter/`)는 ADR-0013 구현과 함께 삭제됐다 |
| [ADR-0007](ADR-0007-bc-hybrid-harness-architecture.md) | B+C 하이브리드 하네스 아키텍처 (문서 기반 상태 머신 + 격리 멀티에이전트) | Accepted (historical, 2026-07-21 추출) | 구현됨 — `state-machine` skill, `orchestrator/planner/implementer/evaluator` agents |
| [ADR-0008](ADR-0008-new-plugin-scaffolding-contract.md) | 신규 플러그인 스캐폴딩 계약 + `packages/` vs `plugins/<name>/` 경계 | Accepted (2026-07-29) | 부분 구현 — lint/CI 자동 탐색은 반영됨, 체크리스트·경계 기준은 플러그인 #2 착수 전까지 미검증 |
| [ADR-0009](ADR-0009-contract-dev-plugin-design.md) | `contract-dev` 플러그인 설계 (1단계: go-stablenet 내장 systemcontracts/) | Accepted (2026-07-31) | 설계만 — `compact-core`형 구조(MCP 서버 없음, skills+리뷰/감사 에이전트) 결정, 실제 스캐폴딩은 별도 작업 |
| [ADR-0010](ADR-0010-stablenet-expert-meta-plugin-design.md) | `stablenet-expert` 메타 플러그인 설계 (1단계: doctor만) | Accepted (2026-07-31) | 구현됨 — PR #12, `check-plugins.sh`/`check-mcp-conflicts.sh` 라이브 검증(실제 coding-agent/core-dev 충돌 3건 정확히 탐지) 완료 |
| [ADR-0011](ADR-0011-stablenet-expert-doctor-interactive-setup.md) | `stablenet-expert:doctor` 2단계 (대화형 수정 + 플러그인별 setup 위임) | Superseded by ADR-0012 (2026-08-03) | 설계만 — `midnight-expert:doctor`의 위임/대화형수정 패턴 채택, `core-dev`의 기존 setup remediation(ADR-0002/0004) 재사용(재구현 안 함). 위임/자체수정 원칙은 ADR-0012에 유지, 스텝 구조만 대체됨 |
| [ADR-0012](ADR-0012-doctor-step-order-revision.md) | `doctor` 스텝 재구성: 공통 환경 체크 + MCP 연결성 체크 + 결정/실행 분리 + MCP 값 비노출 | Accepted (2026-08-03) | 구현됨 — `scripts/check-environment.sh`·`check-mcp-connectivity.sh`·`set-mcp-env.sh` 신규, `commands/doctor.md` 전면 재작성(0-5 6단계), `scripts/check-setup-delegates.sh` 제거·Step 4에 인라인 흡수, `docs/SETUP.md` §9.9 MCP dedup 설명 정정, MCP 연결 값(URL/IP/토큰)이 체크 출력·대화에 노출되지 않도록 정정 |
| [ADR-0013](ADR-0013-retire-jira-gateway-adopt-atlassian-mcp.md) | `jira-gateway` 폐기, 공식 Atlassian MCP로 전환 (ADR-0006 인바운드 절 개정) | Accepted (2026-08-04) · 구현 완료 (2026-08-06) | 구현됨 — 호출부 5파일 전환, `jira-via-atlassian` 스킬(cloudId·도구매핑·3-tier 전이), `.mcp.json`/`REQUIRED`/스키마에서 jira-gateway 제거, Go 패키지·`go.work`·CI 잡 삭제. 인바운드 필터 상실은 명시적 결정 |
| [ADR-0014](ADR-0014-plugin-setup-script-contract.md) | 플러그인 setup 스크립트 계약 (`--check`/`--fix`/`--json`) + doctor의 경로 기반 위임 | Accepted (2026-08-05) | 구현됨 — `core-dev/scripts/setup.py`에 `--json` 추가(용도 설명·시크릿 비노출 계약, `test_setup.py::TestJSONOutput`이 고정), `commands/doctor.md` Step 4를 스킬 호출에서 스크립트 실행으로 교체. ADR-0011 §2.2 위임 원칙은 유지하고 수단만 교체 |
| [ADR-0015](ADR-0015-python-interpreter-selection.md) | Python 인터프리터 선택 정책 | Accepted (2026-08-05) | 구현됨 — 지원 버전을 3.12 하나로 두고(3.9는 upstream EOL, brew가 2026-10-15에 disable), 차단 없이 보고만 하며, 동의한 경우에만 `install-python.sh`로 설치하며, `STABLENET_EXPERT_PYTHON` 절대경로로 참조해 시스템 `python3`와 PATH를 건드리지 않는다. settings `env`의 훅 전달과 `${VAR:-default}` 확장은 실측 검증 |
| [ADR-0016](ADR-0016-naming-and-abbreviations.md) | 명명·약어 규칙 | Accepted (2026-08-05) | 적용 중 — GLOSSARY.md 신설, 삭제된 문서의 `C1`/`C4` 제거, 벤치 문서의 `RI-1..11`을 불변식 번호로 복원. 에이전트 지시문의 `RI-nn` 제거는 파이프라인 영향을 따로 확인하기 위해 후속 PR로 분리. 도메인팩(`domains/**`)은 색인 기준선 보호를 위해 제외 |
| [ADR-0017](ADR-0017-setup-external-plugin-dependencies.md) | 외부 플러그인 의존의 셋업 계약 | Accepted (2026-08-06) | 구현됨 — ADR-0014의 행 스키마를 `row_kind`로 확장하고 Atlassian MCP 설치·OAuth를 `setup_checks/atlassian.py`가 담당. 실행은 `--with-plugins` opt-in(테스트가 머신을 건드리지 않도록), 상태 판정 불가 시 `unknown`으로 행동 보류. CLI 동작 4건은 실측 |

의존 관계: ADR-0001 ← ADR-0002 ← ADR-0004 (도메인팩 → setup/doctor → remediation 라우팅).
ADR-0005는 ADR-0001(도메인팩)을 전제로 한다. ADR-0006·ADR-0007은 독립이며, `HANDOFF.md`(2026-06-05
스냅샷, 삭제됨)에 있던 설계 근거 중 재사용 가치가 있는 부분을 승격한 것이다. ADR-0008은 ADR-0005를
전제로 하며(마켓플레이스 분리가 먼저 결정돼야 "새 플러그인 만드는 법"이 의미가 있음), WORKLIST §B의
멀티플러그인 확장성 항목들을 해소한다. ADR-0009는 ADR-0005 §2.4(contract-dev 범위)와 ADR-0008(신규
플러그인 체크리스트)을 전제로 하며, WORKLIST §B 검증 중 실증된 MCP 서버 이중 등록 충돌(ADR-0008
§2.2의 첫 실제 사례)을 근거로 MCP 서버를 아예 두지 않기로 결정했다. ADR-0010은 ADR-0009와 같은
전제(ADR-0008 체크리스트) 위에 있으며, ADR-0009가 발견한 이중 등록 충돌(`docs/SETUP.md` §9.9)을
자동 탐지로 승격하는 것이 핵심 동기다. ADR-0011은 ADR-0010(doctor 1단계)의 직접 후속이며,
ADR-0002/ADR-0004(core-dev의 doctor→setup remediation 라우팅)를 전제로 재사용한다. ADR-0012는
ADR-0011을 supersede하며, 실제 라이브 실행(2026-08-03)에서 드러난 스텝 구조 문제(공통 환경 체크
부재, MCP 연결성 체크 부재, 결정/실행 미분리, 위임 스텝의 부자연스러운 분리)를 근거로 한다 —
ADR-0011의 위임/자체수정 원칙 자체는 바뀌지 않았다.
ADR-0013은 ADR-0006의 인바운드 절만 부분 supersede한다 — `jira-gateway`(인바운드 필터링의 유일한
구현 지점)를 폐기하기로 한 결정에서 파생됐으며, 아웃바운드(`pr-sanitize`)는 `jira-gateway`와
무관하게 독립적으로 동작해왔으므로 ADR-0006의 해당 절은 그대로 유효하다.
ADR-0003은 독립이며, 검증 절차는 [`../reproduction-verification-runbook-2026-06-23.md`](../reproduction-verification-runbook-2026-06-23.md).

> 비고: 이 ADR들은 각각 단일 토픽을 둘러싼 **응집된 결정 묶음**(보통 결정 4건)으로 작성돼 있어,
> 1결정=1ADR로 분할하지 않고 묶음 단위로 보존했다(문서 proliferation 방지).

---

## 새 ADR 템플릿

```markdown
# ADR-NNNN — <결정 제목>

문서 성격: **ADR / 설계 결정 (<Proposed|Accepted|Superseded> YYYY-MM-DD).**
짝 문서: <관련 코드/문서 링크>

> **결정 한 줄:** <무엇을 왜 이렇게 정했는가>
> **상태:** <Accepted (구현 반영됨) | Proposed | Superseded by ADR-MMMM (이유)>

## 1. Context (왜)
<문제·배경. 코드 근거 cite>

## 2. Decision (무엇)
<결정 내용. 하나의 결정. 대안과 trade-off>

## 3. Consequences (결과)
<긍정·부정 영향, 후속 작업, 검증 방법>
```
