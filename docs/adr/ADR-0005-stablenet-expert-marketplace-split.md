# ADR-0005 — stablenet-expert 마켓플레이스 분리 + core-dev/cq 경계

문서 성격: **ADR / 설계 결정 (Accepted 2026-07-20, §2.3 2026-07-20 재검토 후 revised, §5 이후 추가 —
dapp 로드맵 제외).**
짝 문서: 참조 사례 [`references/midnight-expert`](../../../references/midnight-expert) ·
[VISION.md](../VISION.md) · [ADR-0001](ADR-0001-domain-pack-contract.md)(도메인팩, 이 결정이 전제로 삼음).

> **결정 한 줄:** `coding-agent`를 단일 플러그인 리포에서, midnight-expert와 동일한 구조의
> `stablenet-expert` 멀티플러그인 마켓플레이스로 확장한다. 기존 파이프라인은
> **`core-dev`**로 이름을 바꿔 이관한다(완료). evaluator의 4단계 검증 로직은
> **분리하지 않고 core-dev에 그대로 둔다**(§2.3 — 최초안은 `stablenet-cq` 분리였으나 재검토 후 철회).
> `stablenet-contract-dev`는 Solidity/EVM 스마트컨트랙트로 범위를 한정한다.
> **상태:** Accepted — §2.1/2.2/2.4는 `stablenet-expert` 리포로 이관 완료. §2.3은 "분리 안 함"으로
> 최종 결정. §5(dapp 로드맵 제외)로 §1의 5-카테고리는 4-카테고리로 축소.

---

## 1. Context (왜)

`coding-agent`는 `.claude-plugin/marketplace.json`(단일 플러그인 등록) + `plugin/`(전체 로직) 구조로,
go-stablenet 하나의 Jira 파이프라인만 다룬다. 사용자는 이를 midnight-expert처럼 카테고리별
복수 플러그인 마켓플레이스로 확장하려 한다: dapp 개발 / contract 개발 / 테스트 & 코드 품질 /
툴체인 & 인프라 / **core 개발**(= 현재 coding-agent의 전체 기능). **(§5 참고 — dapp 개발은 이후
로드맵에서 제외됐다. 이 문단은 원 결정 시점의 맥락이라 그대로 둔다.)**

midnight-expert 검토 결과, 그 마켓플레이스는 phase-of-work로 플러그인을 나눈다 — 작성(`compact-core`)
↔ 검증(`midnight-verify`/`midnight-cq`) ↔ 툴체인(`midnight-tooling`) ↔ 지식(`core-concepts`)이 각각
독립 플러그인이고, 마켓플레이스 루트는 콘텐츠를 갖지 않는다(`plugins/*`만 등록, `docs/`·`scripts/`는
리포 관리용이지 배포 대상이 아님).

`coding-agent`의 `evaluator` 에이전트는 이미 이 phase-of-work 경계에 해당하는 일(unit+`-race`,
lint/format, security scan, chainbench 통합)을 하고 있으나, orchestrator의 상태머신을 통해서만
호출 가능한 **pipeline-internal** 로직이라 재사용 불가 — `midnight-cq`처럼 사용자가 직접
`/quality-check`를 돌릴 수 없다.

---

## 2. Decision (무엇)

### 2.1 리포 구조 — `stablenet-expert` (새 리포, midnight-expert 대칭)

```
stablenet-expert/
├── .claude-plugin/marketplace.json   # 6개 plugin 등록
├── packages/                         # jira-gateway-mcp, sensitive-guard 이관
├── scripts/                          # 리포 CI/검증 (contract lint 포함)
├── plugins/
│   ├── core-dev/           # coding-agent 이관 ("core 개발")
│   ├── stablenet-cq/                 # evaluator 분리 신설 ("테스트 & 코드 품질")
│   ├── stablenet-contract-dev/       # 신설 (Solidity/EVM)
│   ├── stablenet-dapp-dev/           # 신설 (범위 미정 — §4)
│   ├── stablenet-tooling/            # 신설 (범위 미정 — §4)
│   └── stablenet-expert/             # meta (생태계 doctor)
├── docs/, bench/                     # 리포 관리용, 배포 대상 아님(coding-agent의 docs/bench와 동일 역할)
└── README.md
```

> 이 트리는 **결정 시점(2026-07-20)의 원안**이다 — 이후 두 가지가 바뀌었다: `stablenet-cq/`는
> §2.3에서 분리하지 않기로 철회됐고, `stablenet-dapp-dev/`는 §5에서 로드맵 제외됐다. 현재 실제
> 구조(발행 1개 + 계획 3개)는 [README.md](../../README.md#plugins)가 최신 소스다.

`stablenet-knowledge`·`chainbench`는 sibling repo로 유지, `.mcp.json` 경로/URL 참조만 이관.

### 2.2 네이밍 — `core-dev`

`<도메인>-<역할>` 컨벤션(`compact-cli-dev`, `midnight-dapp-dev` 등)을 따르고 "core 개발" 카테고리와
1:1 대응. `stablenet-core`(지식 전용 플러그인과 혼동), `stablenet-agent`(Claude Code `agents/`
개념과 용어 충돌)는 기각.

### 2.3 `stablenet-cq` 분리 — REVISED: 분리하지 않는다 (2026-07-20 재검토)

**최초안(철회):** unit+`-race`, lint/format, security scan, chainbench 통합 실행 로직을
`stablenet-cq`(신설 플러그인)의 skills + `cq-reviewer`/`cq-runner` 에이전트(midnight-cq 패턴)로
분리하고, core-dev의 evaluator를 그걸 호출하는 얇은 래퍼로 재정의한다는 안이었다.

**철회 사유 — 기계적으로는 가능하지만 이득이 비용을 못 이긴다:**

1. **domain-pack 접근 경계.** evaluator는 `${CLAUDE_PLUGIN_ROOT}/domains/{project_id}/domain-pack.json`
   에서 `ver.build`/`ver.unit_test.*`/`ver.stages`를 읽는다. `CLAUDE_PLUGIN_ROOT`는 **플러그인
   인스턴스마다 다른 값**이라 `stablenet-cq`로 옮기면 core-dev의 `domains/go-stablenet/`을 이
   경로로 못 찾는다. 해결책은 domain-pack을 cq에도 복제(SSoT 두 개, drift) 또는 core-dev가 매번
   검증 계약 전체를 프롬프트로 인라인 전달(cq를 순수 실행기로 격하) 뿐 — 둘 다 지금보다 나쁘다.
2. **MCP 서버 중복.** chainbench 통합 스테이지(§7)가 cq로 가면 cq도 자기 `.mcp.json`에 chainbench를
   따로 등록해야 하고, 사용자는 `CHAINBENCH_DIR` 등을 두 플러그인에 각각 설정해야 한다.
3. **버전 drift 게이트 부재.** MCP 도구명 drift는 `scripts/contract/lint-tool-names.sh`가 잡지만,
   "core-dev → cq 프롬프트 스키마" drift를 잡는 장치는 없다. 두 플러그인이 마켓플레이스에서 독립
   버전으로 설치되므로 조용히 어긋날 수 있다.
4. **아티팩트 핸드오프 추가 홉.** `test-report.md`/`eval-*.log`는 지금 evaluator가 `workspace_dir`
   (타깃 리포 안)에 직접 쓴다. cq가 별도 플러그인 컨텍스트에서 실행되면 텍스트로 반환받은 뒤
   core-dev가 다시 파일로 마샬링해야 하는 단계가 하나 늘어난다.
5. **재사용 명분 자체가 약하다 (결정적).** evaluator §4.1의 "변경된 테스트 함수 탐지"는
   `git diff | grep -E '^\+func (Test|Fuzz)...'`처럼 **Go 문법을 프롬프트에 하드코딩**한다.
   Stage 1–3(unit/lint/security)의 실제 명령은 domain-pack이 주지만(`go test`/`golangci-lint`/
   `gosec`), 그 명령을 조립하는 절차 자체가 Go 전용이다. 그런데 §2.4에서 `stablenet-contract-dev`를
   **Solidity/EVM**로 확정했다 — 완전히 다른 툴체인(Foundry/Hardhat, solhint, slither)이 필요하다.
   즉 지금 evaluator/cq 로직은 애초에 contract-dev나 dapp-dev가 재사용할 수 있는 게 아니다.
   "분리해서 다른 플러그인이 재사용하게 하자"는 원래 명분이 contract-dev 범위 확정 순간 무너진다.

**최종 결정:** evaluator는 `core-dev` 안에 그대로 둔다. `reproduce-first`·
`simulation-harness`·`root-cause-lifecycle`·`state-machine` 스킬과 `EVALUATION_FAIL`→bugfix
재진입 판단(orchestrator)도 당연히 core-dev 잔류(이건 원안에서도 분리 대상이 아니었다 — 버그
진단 방법론이자 상태머신과 결합된 제어 흐름이라 분리하면 재현(RED→GREEN) 규율이 깨진다).

**대안(미착수, 필요 시 별도 작업):** "Jira 없이 품질체크만 돌리고 싶다"는 원래 니즈는 core-dev
안에 티켓 없이 evaluator를 직접 구동하는 가벼운 커맨드(예: `/core-dev:check`)를
추가하는 것으로 크로스플러그인 비용 없이 해결 가능 — 필요해지면 별도 ADR/작업으로.

진짜 별도 `stablenet-cq`(또는 도메인별 검증 플러그인)는 `stablenet-contract-dev`(Solidity)가 실제로
만들어지고 자기 검증 로직이 필요해지는 시점에, 지금 evaluator를 감싸는 형태가 아니라 **그 도메인
전용으로 새로 설계**하는 게 맞다.

### 2.4 `stablenet-contract-dev` 범위

go-stablenet(geth fork + WBFT)은 EVM 호환이므로, Solidity 스마트컨트랙트 작성/리뷰/보안감사로
한정한다(`compact-core`의 대응물). WBFT·런타임 등 체인 코어 개발은 명시적으로 이 플러그인
범위 밖.

---

## 3. Consequences (결과)

- **+**: 카테고리↔플러그인 네이밍이 사용자 멘탈모델과 1:1 대응, midnight-expert와 구조 대칭 유지.
- **+**: §2.3을 분리하지 않기로 하면서 domain-pack 접근 경계·MCP 중복·크로스플러그인 drift 게이트
  부재 같은 리스크를 애초에 만들지 않았다. evaluator는 지금처럼 하나의 플러그인 안에서 상태머신·
  재현 스킬과 강결합된 채로 남는다.
- **−/제약**: "Jira 없이 품질체크"라는 원래 니즈는 아직 미해결 — `/core-dev:check` 같은
  가벼운 대안은 설계만 됐고 미구현.
- **후속**:
  1. `stablenet-tooling` 범위는 go-stablenet 실제 노드 운영 툴링 대비 미검토 — 별도 조사 필요
     (`stablenet-dapp-dev`는 §5에서 로드맵 제외돼 이 항목에서 뺐다).
  2. `stablenet-contract-dev`(Solidity)가 실제로 만들어지면, 그 도메인 전용 검증 플러그인이
     필요한지는 그때 별도 ADR로 재검토.
  3. (선택) `/core-dev:check` 커맨드 — 별도 작업으로 필요 시 진행.

## 4. 실행 상태 (2026-07-20)

- §2.1(리포 구조)·§2.2(네이밍)·§2.4(contract-dev 범위): **완료** — `/Users/wm-it-25_0220/Work/github/stablenet-expert`로
  `git ls-files` 기준 기계적 이관 + 경로/도구명 참조 수정(`mcp__plugin_coding-agent_*` →
  `mcp__plugin_core-dev_*` 포함) + `go build`/`go test`/`lint-tool-names.sh`/파이썬
  유닛테스트로 검증 완료.
- §2.3(cq 분리): **철회** — 위 재검토 사유로 분리하지 않기로 최종 결정.

## 5. dapp 개발 로드맵 제외

**결정:** `stablenet-dapp-dev`(§1의 5-카테고리 중 하나)는 로드맵에서 제외한다. 사용자 지시로
`README.md`의 "Planned categories" 표에서 뺐다(정확한 날짜는 이 리포 대화 기록 참고 — 이 ADR
자체에는 재구성 시점을 단정하지 않는다).

**범위:** 로드맵 축소일 뿐, §2.3(evaluator 재사용 불가 논증)이나 §2.4(contract-dev 범위)는
dapp 여부와 무관하게 그대로 유효하다. §1/§2.1의 dapp 언급은 삭제하지 않고(ADR 원칙 —
[docs/adr/README.md](README.md) "삭제 금지, supersede만") 위 두 지점에 이 절을 가리키는
주석만 남겼다.

**현재 로드맵(4-카테고리):** `core-dev`(발행 완료) + `stablenet-contract-dev`/`stablenet-tooling`/
`stablenet-qa`(계획, 미착수). `stablenet-qa`는 §2.3 최종 결정(evaluator는 core-dev 잔류)과 실질적으로
같은 상태를 가리키는 이름일 뿐 — §2.3 자체가 번복된 게 아니라, "미래에 이 결정을 재검토할 수도
있다"는 가능성만 이름으로 열어둔 것이다. 메타 플러그인(`stablenet-expert`)은 위 셋 중 하나가
발행된 뒤에나 착수 대상. 최신 상태는 [`docs/WORKLIST.md`](../WORKLIST.md) §A.
