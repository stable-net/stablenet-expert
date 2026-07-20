# Stablenet Context — path→module classification (drift-free helper)

> Domain-pack data for `go-stablenet`. The path→module map and complexity heuristic
> below are go-stablenet-specific DATA; the `classify_domain`/`estimate_complexity`
> *procedure* wrappers are generic and will move to the `domain-pack` loader skill in
> Phase 2. Moved here from `skills/stablenet-context/SKILL.md` in overlay P1 Phase 1.
> Domain *knowledge* (invariants, system-contract names, consensus rules) is NOT here
> — it comes from cks live + the `invariants.md` backstop (see domain-pack.json).

## 1. 권위 있는 도메인 지식 출처 (이 데이터 아님)

도메인 판단·불변식·테스트 권장은 다음에서 온다:

- **cks 라이브 검색** — `cks.context.get_for_task` / `cks.context.semantic_search`
  응답의 `guidance` 필드(`watch_out` / `also_review` / `required_tests`).
  이 값은 ckv `policy/stablenet.yaml`(런타임 SSoT 뷰)에서 주입된다.
- **cks 도메인 엔트리** — `code-knowledge-system/docs/domain-knowledge/projects/
  go-stablenet/entries/*.yaml` (`code_anchors`, `invariants`, `pitfalls`).
- **항상-켜진 backstop** — `invariants.md` (byzantine-fairness 핵심 불변식 L3 주입).
  System contract 이름·합의 엔진 등 고정 사실은 거기서 관리한다.

System contract 이름이나 합의 규칙을 이 파일에서 찾지 말 것 — 위 출처를 쓴다.

---

## 2. 경로 기반 모듈 분류 (drift-free)

```
file_path contains "consensus/"                        → consensus
file_path contains "governance-wbft/" or "governance/" → governance
file_path contains "core/txpool/"                      → txpool
file_path contains "core/state/" or "trie/"            → state
file_path contains "core/" (and not above)             → core
file_path contains "p2p/"                              → p2p
file_path contains "rpc/" or "internal/ethapi/"        → rpc
file_path contains "miner/"                            → miner
file_path contains "params/"                           → params
file_path contains "cmd/"                              → cmd
file_path contains "eth/" or "les/"                    → eth/les
```

동시성 민감 모듈(`-race` 및 `concurrency_impact` 대상): `consensus`, `core/txpool`,
`core/state`, `miner`. 단, 권위 있는 동시성 범위는 cks
`cks.context.concurrency_impact` 응답이며, 이 목록은 시드 선정용 힌트일 뿐이다.

---

## 3. 제공 함수 (절차 — Phase 2에서 제너릭 로더로 이동 예정)

### 3.1 classify_domain(file_paths, symbols)

**절차**: 각 `file_path`를 §2 규칙으로 분류 → 중복 제거 → 빈도순 정렬.
`symbols`는 경로가 모호할 때 보조로만 쓰되, **contract 이름 기반 분류는 하지
않는다**(drift 원인). 심볼이 어느 파일에 정의됐는지 모르면 cks
`cks.context.find_symbol` 로 경로를 얻어 §2 규칙을 적용한다.

**출력**:
```jsonc
{ "primary_domain": "consensus", "domains": ["consensus","core"], "confidence": "high|medium|low" }
```
`confidence`는 경로 신호의 일관성(같은 모듈로 수렴하면 high)으로 정한다.

### 3.2 estimate_complexity(domains, change_summary)

**절차**:
```
simple   : domains 1개 + 동시성 무관
moderate : domains 1-2개 + 동시성 일부 관련
complex  : 다음 중 하나라도 —
           domains >= 3
           consensus | txpool | state | miner 중 포함
           change_summary 에 "genesis" | "hardfork" | "system contract" 키워드
           cross-module 의존
```
동시성 키워드(`goroutine`/`race`/`mutex`/`concurrent`)가 보이면 한 단계 올린다.

**출력**:
```jsonc
{ "complexity": "simple|moderate|complex", "reasoning": "..." }
```

도메인별 불변식·권장 테스트·byzantine-fairness 판단은 이 함수가 아니라 cks
`get_for_task` 의 `guidance` 와 `invariants.md` backstop에서 온다.
