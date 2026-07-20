# Handoff — coding-agent A/B 개선 + pr-77 인덱스 재정비 (2026-06-19)

> 다른 머신/세션에서 이 작업을 **그대로 이어서** 진행하기 위한 자족(self-contained) 문서.
> 절대경로는 모두 이 머신 기준(`/Users/wm-it-25_0220/Work/github/...`)이며, 새 머신에선
> 워크스페이스 루트만 바꿔 읽으면 된다. **인덱스 DB와 빌드 바이너리는 머신-로컬이라
> 새 머신에선 재빌드해야 한다**(§5, §6 런북 참조).

---

## 0. 60초 요약 — 지금 어디까지 왔나 / 다음 한 가지

**목표**: coding-agent 파이프라인이 *관찰-한정(lean) 증상 입력*만으로 버그 근본 원인을
정확히 찾도록 개선. 두 축 —
- **A (규율)**: analyzer 에이전트 + comprehension 스킬(생애주기 추적·anti-confirmation·effect-completeness·probe).
- **B (검색)**: cks `find_callers`의 **인터페이스-디스패치 브릿지**(concrete method → 구현 인터페이스 메서드의 호출자까지 회수).

**현재 상태**: A·B 모두 구현·커밋 완료. pr-77 인덱스(ckg+ckv)를 *make gstable 빌드 범위 +
.sol 컨트랙트 + 테스트 포함*으로 재빌드해 라이브 적용 완료. 검증 3건 통과:
- STABLE-0005(PR-77) lean diagnose ×2 → **정답 도달**(expert-fix.diff와 일치).
- STABLE-0002 lean diagnose → **다른 메커니즘(동시성 race)** 정확히 규명 = 일반화 입증.

**다음 한 가지(택1)**:
- (권장) **Task #5 full bugfix 라이브 런** — `/coding-agent:analyze` 또는 bench 매니페스트로 PR-77을 end-to-end(analyzer→planner→implementer→evaluator) 자율 수정시키고 expert-fix와 비교.
- 또는 **Task #3 추가 일반화** — STABLE-0009/0007 diagnose 1~2건 더.

**완전 새 머신**이라면 먼저 **§4A(부트스트랩: 레포 클론·설정 생성·ollama·플러그인)** →
**§5(인덱스 재빌드)** → **§6(MCP 기동)** 순으로 환경을 갖춰야 한다. (이미 이 작업을 돌려본
머신이라면 §5부터.) `knowledge-data/`는 **git 버전관리 대상이 아니라** 설정/인덱스가 레포로
전달되지 않으므로, 설정 전문을 §4A에 embed해 두었다.

---

## 1. 레포 구성 (멀티레포)

| 레포 | 역할 |
|---|---|
| `coding-agent` | Claude Code **플러그인**(agents/skills/commands/hooks/.mcp.json). 우리가 개선하는 대상. |
| `code-knowledge-system` (cks) | ckg+ckv를 in-process 합성, MCP 툴 노출. **라이브 find_callers는 여기 구현**(ckg mcphandlers 아님). |
| `code-knowledge-graph` (ckg) | 콜그래프/심볼 그래프(SQLite). schema_version 1.21. |
| `code-knowledge-vector` (ckv) | bge-m3 임베딩 벡터 인덱스(SQLite + sqlite-vec). |
| `chainbench` | go-stablenet e2e 하니스(MCP). evaluator가 사용. |
| `test/pr-77` | 대상 코드(go-ethereum 포크 go-stablenet) **PR-77 부모 = 버그 실재** 체크아웃. |

---

## 2. 이번 세션에서 한 일

### 2.1 A — analyzer 분리 + 규율 스킬 (coding-agent, main에 커밋됨)
- `planner`를 `analyzer`(ANALYSIS 단계) + `planner`(PLANNING/DESIGN)로 분리.
  4-stage 파이프라인: **analyzer → planner → implementer → evaluator**, EVALUATION_FAIL 시 analyzer 재진입.
- analyzer 소유: 상황분석(cks) + 재현 테스트(RED) + 근본원인(root-cause-lifecycle).
- 스킬: `root-cause-lifecycle`(생애주기 produce→store→consume + 시계열 + 다중후보 + **effect-completeness** + **anti-confirmation**), `reproduce-first`(red→green 오라클), `investigative-probe`(후보 disambiguation용 throwaway 런타임 프로브).
- diagnose 커맨드(`/coding-agent:diagnose`): analyzer를 **읽기전용 진단 모드**로 재사용(코드/브랜치/PR 무변경, diagnosis.md만 산출).

### 2.2 B — 인터페이스-디스패치 브릿지 (핵심 발견 포함)
- **문제**: Go 인터페이스 호출은 ckg에서 `invokes` 엣지가 **인터페이스 메서드 노드**(`pkg.I.M`)로 기록됨. concrete method(`pkg.T.M`)에서 역방향 walk만 하면 인터페이스 경유 호출자를 **전부 놓침** → `find_callers`가 self-edge만 반환.
- **함정(이번 세션의 큰 교훈)**: 브릿지를 처음 **ckg `pkg/mcphandlers`** 에 구현했으나, **라이브 cks는 그 코드를 안 씀**(cks는 `internal/ckgclient/real.go`의 `Neighbors`로 ckg reader를 직접 호출). 그래서 인덱스를 올려도 라이브가 안 고쳐졌음.
- **해결**: 동일 브릿지를 **cks `internal/ckgclient/real.go`** 에 포팅 —
  `interfaceMethodSeeds(methodQname)`(implements 엣지로 인터페이스 메서드 시드 도출) +
  `Neighbors`가 reverse(callers) walk일 때 concrete seed와 인터페이스 메서드 시드를 union.
  일반화 유지(forward walk·비-메서드·implements 없으면 no-op). 단위테스트 추가.
- **현재 위치**: cks `origin/main`(88b6454)에 포함됨(`grep interfaceMethodSeeds internal/ckgclient/real.go` = 4 hits로 검증). ckg쪽 mcphandlers 브릿지도 ckg main에 존재(부수적, cks는 안 씀).

### 2.3 인덱스 재빌드 (knowledge-data/pr-77)
- **계기**: 사용자 지적 — (1) DB가 .sol을 빠뜨렸고(go-only), (2) 전체 트리라 make gstable 범위로 한정해야 함, (3) 테스트도 DB에 포함하되 쿼리시 필터링.
- **오염 검증 결론**: 인덱싱한 `0bf2f4d1b`는 **PR-77 부모(버그 실재)** 임을 코드로 확인 — `eth/gasprice/anzeon.go:54`는 버그 가드(`currentBlock.Root != header.Root`, 수정의 `|| gasTipChanged` 없음), `core/txpool/legacypool/legacypool.go` `RemotesBelowTip`도 버그(`GasTipCapIntCmp`). 따라서 **diagnose 성공은 오염 아님**.
- **재빌드 범위**: `go list -deps ./cmd/gstable`의 in-module 패키지 **129개**의 `*.go`(테스트 포함) + `systemcontracts/**/*.sol`. ts/proto 제외. files-from = `knowledge-data/pr-77/gstable-files.json`.
- **결과**:
  - ckg: schema 1.21, nodes 183,008 / edges 1,603,394, go 988(빌드668+테스트320) + sol 22파일(841 노드). `--at-commit 0bf2f4d1b` clean worktree 빌드.
  - ckv: bge-m3 dim1024, chunks 15,575(go 15,058 + sol 388), canonical_id 정렬 87%(13,549/15,575).
  - 둘 다 temp(`ckg.rebuild2`/`ckv.rebuild`)에 빌드 → 검증 → swap. 백업: `ckg.bak-1.15`(원본 schema1.15), `ckg.bak-go-wholetree`(중간 go-only), `ckv.bak-wholetree`(원본 전체트리).

### 2.4 검증 (모두 진단모드, 코드 무변경)
| 케이스 | 입력 | 결과 |
|---|---|---|
| B 스모크 | `find_callers(gasprice.AnzeonTipEnv.GetAnzeonTipCap)` | `ValidateTransactionWithState`·`EffectiveGasTip` 회수 ✓ (이전 self-edge only) |
| STABLE-0005 #1 | lean 증상 | 근본원인 = `SetCurrentBlock` root-동등 가드 → 정답 ✓ |
| STABLE-0005 #2 (canonical, sol 인덱스) | lean 증상 | 동일 정답, **expert-fix.diff와 일치** ✓ |
| STABLE-0002 | lean 증상 | **다른 메커니즘**(detached goroutine race, `blockchain.go:1857`) 정확 규명 = 일반화 ✓ |

진단 산출물: `coding-agent/.coding-agent/diagnoses/DIAG-20260619_103718`(0005#1), `DIAG-20260619_121340`(0005 canonical), `DIAG-20260619_122858`(0002).

---

## 3. 레포 git 상태 (이 세션 종료 시점)

| 레포 | 브랜치 | HEAD | 비고 |
|---|---|---|---|
| coding-agent | main | `01569b2` | analyzer 분리·스킬·diagnose 모두 커밋됨. 클린. |
| code-knowledge-system | main | `88b6454` | **B 브릿지 포함**(origin/main 동기화). 클린. |
| code-knowledge-graph | main | `e74ce15` | mcphandlers 브릿지 포함. cks go.mod는 ckg `v0.0.0-...-1ab59602cf49` 핀. |
| code-knowledge-vector | feat/ckv-invariants-pkg | `a4cec74` | cks go.mod는 ckv `v0.0.0-...-c554cc5d5cd2` 핀. |
| test/pr-77 | (detached) | `0bf2f4d1b` | PR-77 부모(버그). 추적 변경 없음(untracked docs/.claude만). |

> 주의: 이 레포들은 **여러 세션/머신이 공유**한다. 이어받기 전 각 레포에서
> `git fetch && git status`로 최신 origin 상태를 확인하라(이 세션 중에도 cks 브랜치가
> 다른 세션에 의해 main으로 동기화된 적 있음).

---

## 4. pr-77 인덱스 & cks 설정 (다른 머신에서 가장 중요)

### 4.1 위치/설정 파일
```
knowledge-data/pr-77/
├── ckg/            # 라이브 그래프 (schema 1.21, gstable+sol+tests)
├── ckv/            # 라이브 벡터 (bge-m3)
├── ckg.bak-1.15, ckg.bak-go-wholetree, ckv.bak-wholetree   # 백업
├── cks-pr77.yaml   # cks MCP 설정
├── gstable-files.json  # files-from(재빌드 재현용 산출물)
```

`cks-pr77.yaml` 핵심:
```yaml
ckg: { path: .../knowledge-data/pr-77/ckg/graph.db, binary: .../code-knowledge-graph/bin/ckg, source_root: .../test/pr-77 }
ckv: { path: .../knowledge-data/pr-77/ckv, binary: .../code-knowledge-vector/bin/ckv, embed_model: bge-m3, ollama_url: http://127.0.0.1:11434 }
```

### 4.2 Claude Code가 cks를 띄우는 경로 — `~/.claude/settings.json`
```json
"CKS_MCP_BIN": ".../code-knowledge-system/bin/cks-mcp",
"CKS_CONFIG":  ".../knowledge-data/pr-77/cks-pr77.yaml"
```
플러그인 `.mcp.json`의 `cks` 서버가 `${CKS_MCP_BIN} -config ${CKS_CONFIG}`로 **stdio** 기동.

### 4.3 크로스머신 주의
- **인덱스 DB는 머신-로컬·대용량**(ckg ~627MB, ckv ~90MB). 새 머신엔 없으니 **§5로 재빌드**하거나 복사.
- **절대경로**가 settings.json·cks-pr77.yaml·gstable-files는 상대경로에 박혀있다 — 새 머신 경로로 치환.
- **ollama + bge-m3** 필요: `ollama` 데몬 + `bge-m3:latest` 모델 (`curl -s http://127.0.0.1:11434/api/tags`로 확인).
- **go 툴체인**: 이 머신은 gvm(`~/.gvm/gos/go1.25.11`), 비대화 셸엔 PATH 없음 → 빌드/`go list`는 **`zsh -lic '...'`**(로그인 셸)로 실행. 사설 모듈: `export GOPRIVATE="github.com/0xmhha/*"`.

---

## 4A. 부트스트랩 — 완전 새 머신에서 0부터

> `knowledge-data/`(설정·인덱스 DB)와 `test/pr-77`(대상 코드)은 **버전관리되지 않거나
> 별도 레포**라 coding-agent 클론만으론 안 온다. 아래로 환경을 갖춘 뒤 §5(재빌드)로 간다.
> `WG`=워크스페이스 루트(예: `~/Work/github`).

### 4A.1 레포 클론 (모두 `0xmhha`/`stable-net` 오너)
```bash
cd $WG
git clone https://github.com/0xmhha/coding-agent.git
git clone https://github.com/0xmhha/code-knowledge-system.git
git clone https://github.com/0xmhha/code-knowledge-graph.git
git clone https://github.com/0xmhha/code-knowledge-vector.git
git clone https://github.com/0xmhha/chainbench.git           # evaluator용(선택, #5에서 필요)
# 대상 코드 = go-stablenet, PR-77 부모(버그)로 체크아웃:
git clone https://github.com/stable-net/go-stablenet.git test/pr-77
git -C test/pr-77 checkout 0bf2f4d1bfeb6605006d556957ef8c045d8f8ed8   # tag v1.0.0-25-g0bf2f4d1b (버그 부모)
```
브랜치 핀(§3): cks `main`, ckg `main`, ckv `feat/ckv-invariants-pkg`. 클론 후 §3 표와 대조.

### 4A.2 go 툴체인 + 사설 모듈
- go 1.25+ (이 머신은 gvm `~/.gvm/gos/go1.25.11`). 비대화 셸 PATH 없으면 `zsh -lic`로 실행.
- `export GOPRIVATE="github.com/0xmhha/*"` (cks가 ckg/ckv 사설 모듈 당겨옴; git이 0xmhha에 인증돼 있어야).

### 4A.3 ollama + bge-m3 (ckv 임베딩에 필수)
```bash
# ollama 설치(brew install ollama 등) 후 데몬 기동, 모델 받기:
ollama pull bge-m3
curl -s http://127.0.0.1:11434/api/tags   # bge-m3:latest 보이면 OK
```

### 4A.4 `knowledge-data/pr-77/` 디렉터리 + 설정 파일 생성 (VCS 안 됨 → 수기 생성)
```bash
mkdir -p $WG/knowledge-data/pr-77/logs/{footprint,audit}
```
`$WG/knowledge-data/pr-77/cks-pr77.yaml` (경로의 `/Users/.../Work/github`만 `$WG`로 치환):
```yaml
version: 1
backends:
  ckg:
    path: "<WG>/knowledge-data/pr-77/ckg/graph.db"
    source_root: "<WG>/test/pr-77"
    binary_path: "<WG>/code-knowledge-graph/bin/ckg"
    timeout_ms: 5000
  ckv:
    path: "<WG>/knowledge-data/pr-77/ckv"
    timeout_ms: 3000
    embed_model: "bge-m3"
    ollama_url: "http://127.0.0.1:11434"
    binary_path: "<WG>/code-knowledge-vector/bin/ckv"
listen: { http_addr: "127.0.0.1:8080", mcp_stdio: true }
logging:
  level: "info"
  mode: "prod"
  footprint_dir: "<WG>/knowledge-data/pr-77/logs/footprint"
  audit_dir: "<WG>/knowledge-data/pr-77/logs/audit"
sanitize:
  rules_path: "<WG>/code-knowledge-system/policies/sanitization_rules.yaml"
  default_action: "drop"
  fail_closed_on_unknown_rule: true
```
> 대안: `code-knowledge-system/scripts/gen-cks-config.sh`는 현재 체크아웃 경로에서 config+env를
> 자동 생성(단 이름이 `cks-stablenet.yaml`; pr-77용은 위를 직접 쓰는 게 명확).

### 4A.5 Claude Code에 환경변수 + 플러그인 등록
`~/.claude/settings.json`의 `env`에:
```json
"CKS_MCP_BIN": "<WG>/code-knowledge-system/bin/cks-mcp",
"CKS_CONFIG":  "<WG>/knowledge-data/pr-77/cks-pr77.yaml"
```
(참고용 `cks-pr77.env`: 위 둘 + `CKV_OLLAMA_ENDPOINT=http://127.0.0.1:11434`.)
플러그인: `coding-agent/.claude-plugin/marketplace.json`로 marketplace 등록 후 `coding-agent`
플러그인 설치 → `.mcp.json`의 `cks`/`chainbench` 서버가 위 env로 stdio 기동.

### 4A.6 이후
→ §5(바이너리 빌드 + 인덱스 재빌드) → §6(`/mcp` 기동) → §9(재검증).

---

## 5. 인덱스 재빌드 런북 (새 머신/재현)

> 원칙: **temp에 빌드 → 검증 → swap**(라이브 in-place 빌드 금지, 데이터셋 오염 방지).
> 모든 go 명령은 `zsh -lic`로(gvm). `WG=<워크스페이스 루트>`로 치환.

### 5.0 바이너리 빌드
```bash
zsh -lic 'export GOPRIVATE="github.com/0xmhha/*"
cd $WG/code-knowledge-graph   && go build -o bin/ckg ./cmd/ckg
cd $WG/code-knowledge-vector  && go build -o bin/ckv ./cmd/ckv
cd $WG/code-knowledge-system  && go build -o bin/cks-mcp ./cmd/cks-mcp'
```

### 5.1 make gstable 빌드 클로저 → files-from 재생성
```bash
zsh -lic 'cd $WG/test/pr-77 && go list -deps ./cmd/gstable' \
  | grep '^github.com/ethereum/go-ethereum' > /tmp/gstable-pkgs.txt
python3 - <<'PY'
import json
prefix="github.com/ethereum/go-ethereum"
dirs=sorted({l.strip()[len(prefix):].lstrip("/") for l in open("/tmp/gstable-pkgs.txt") if l.strip()})
include=[(f"{d}/*.go" if d else "*.go") for d in dirs]+["systemcontracts/**/*.sol"]
json.dump({"include":include,"exclude":[]},open("<WG>/knowledge-data/pr-77/gstable-files.json","w"),indent=2)
PY
```
> `exclude:[]` = **테스트 포함**(사용자 지침: 테스트는 사용법·의도·수정 예시라 DB에 넣고,
> 평소 결과에선 `exclude_tests` 쿼리 플래그로 필터). 빌드-only를 원하면 `exclude:["**/*_test.go"]`.

### 5.2 ckg 재빌드 (버그 부모에서 clean worktree)
```bash
zsh -lic 'export GOPRIVATE="github.com/0xmhha/*"; cd $WG
$WG/code-knowledge-graph/bin/ckg build \
  --src=$WG/test/pr-77 \
  --at-commit 0bf2f4d1bfeb6605006d556957ef8c045d8f8ed8 \
  --files-from=$WG/knowledge-data/pr-77/gstable-files.json \
  --out=$WG/knowledge-data/pr-77/ckg.rebuild \
  --lang=go,sol --log-file=$WG/knowledge-data/pr-77/ckg-rebuild.log'
```
검증: `sqlite3 ckg.rebuild/graph.db` + `grep schema_version ckg.rebuild/manifest.json`(=1.21),
sol 노드 존재, `find_callers` 브릿지용 엣지(아래) 존재 후 swap.

### 5.3 ckv 재빌드 (bge-m3/ollama, ~20-29분)
```bash
zsh -lic 'export GOPRIVATE="github.com/0xmhha/*"; cd $WG
$WG/code-knowledge-vector/bin/ckv build \
  --src=$WG/test/pr-77 \
  --out=$WG/knowledge-data/pr-77/ckv.rebuild \
  --files-from=$WG/knowledge-data/pr-77/gstable-files.json \
  --lang=go,sol --embedder=ollama --model-name=bge-m3 \
  --ckg=$WG/knowledge-data/pr-77/ckg'
```
> `--ckg` 지정 시 canonical_id 정렬(ckv #9). ckv build엔 `--at-commit` 없음 →
> `--src` 워킹트리(추적분 = 버그 부모)에서 빌드, files-from가 untracked 제외.

### 5.4 swap (백업 후 교체)
```bash
cd $WG/knowledge-data/pr-77
mv ckg ckg.bak-prev && mv ckg.rebuild ckg
mv ckv ckv.bak-prev && mv ckv.rebuild ckv
```

### 5.5 swap 전 ckg 회귀 스모크 (브릿지 엣지 존재 확인)
```sql
-- 버그/브릿지 핵심 엣지가 새 그래프에 있는지
sqlite3 ckg/graph.db "SELECT sn.qualified_name, dn.qualified_name, e.type
 FROM edges e JOIN nodes sn ON e.src=sn.id JOIN nodes dn ON e.dst=dn.id
 WHERE dn.qualified_name LIKE '%AnzeonGasTipEnv.GetAnzeonTipCap%' AND e.type='invokes';"
-- 기대: txpool.ValidateTransactionWithState | types.AnzeonGasTipEnv.GetAnzeonTipCap | invokes
```

---

## 6. MCP 재기동 절차 (Task #4 — 헷갈리기 쉬운 부분)

cks는 두 가지로 뜰 수 있다:

### 6.1 stdio (현재 사용 방식 — 권장)
- Claude Code가 플러그인 `.mcp.json`의 `cks` 서버를 **세션마다 서브프로세스로** 기동.
  툴 네임스페이스 `mcp__plugin_coding-agent_cks__*`. 라이브 진단/work가 쓰는 경로.
- **새 바이너리·새 인덱스를 반영하려면**: 셸에서 stale 프로세스 정리 후 Claude Code에서 **`/mcp` → cks → reconnect**(또는 Claude Code 재시작).
  ```bash
  pkill -f 'bin/cks-mcp -config .*cks-pr77.yaml'   # stale 서브프로세스 정리
  # 이후 Claude Code에서 /mcp 재연결 → 새 CKS_MCP_BIN + 새 graph.db로 재기동
  ```
- 확인: `cks_ops_health` → `ckg.schema_version`, `ckv.last_index_at`, `data_path`가 의도한 값인지.

### 6.2 HTTP 데몬 (`code-knowledge-system/scripts/cks-mcpd.sh`)
- 여러 cks 인스턴스를 포트로 띄워 세션 간 공유. 툴 네임스페이스 `mcp__cks-<name>__*`(플러그인 기대 네임스페이스와 **다름**).
- `cks-mcpd.sh start/stop/restart/list/register <name>`. **현재 미사용**(list 비어있음).
- 플러그인 에이전트 검증엔 stdio가 맞다. 데몬은 다인스턴스/원격 시나리오용.

### 6.3 언제 무엇을 재빌드/재기동?
| 바꾼 것 | 재빌드 | 재기동 |
|---|---|---|
| cks 소스(예: 브릿지) | `bin/cks-mcp` | `/mcp` reconnect |
| ckg/ckv 소스 | `bin/ckg`/`bin/ckv` → **인덱스 재빌드**(§5) | `/mcp` reconnect |
| 인덱스 DB만 swap | — | `/mcp` reconnect |
| ckg/ckv 버전 핀(go.mod) | cks `go get @main` 후 `bin/cks-mcp` | `/mcp` reconnect |

---

## 7. 남은 작업

- **#3 일반화 (진행중)**: STABLE-0002 통과. 선택적으로 STABLE-0009(config override 미반영 타이밍)/0007(genesis Account.Extra 불일치) diagnose 1~2건 더 → "PR-77 전용 아님" 보강.
- **#4 MCP 재기동 문서화**: 본 문서 §6가 사실상 그 산출물. 별도 상시 문서로 승격할지 결정.
- **#5 full bugfix 라이브 런 (권장 다음)**: PR-77을 4-stage end-to-end 자율 수정.
  - 방법: `/coding-agent:analyze "<STABLE-0005 lean 증상>"` (autopilot) 또는 bench 매니페스트 `bench/manifests/stablenet-pr77.json`.
  - **사전조건**: §5 인덱스 라이브 + §6 MCP 기동 + `test/pr-77`에서 implementer가 편집할 수 있는 상태(throwaway 브랜치).
  - **평가**: 에이전트 diff vs `bench/fixtures/pr77/expert-fix.diff`(2파일 23줄) — 파일 overlap(anzeon.go+legacypool.go), 핵심 심볼(SetCurrentBlock/RemotesBelowTip) touch, 동일 근본원인 여부.
  - **종료 후**: `test/pr-77`의 throwaway 브랜치/커밋 정리(데이터셋 오염 방지).

---

## 8. 핵심 사실 / 함정 (이어받기 전 숙지)

1. **0bf2f4d1b = PR-77 부모 = 버그 실재**(오염 아님). 정답 수정은 별도 커밋 `98f05c2a0`. expert-fix.diff = `git diff 0bf2f4d1b 98f05c2a0` = 2파일:
   - `eth/gasprice/anzeon.go`: `SetCurrentBlock` 가드에 `|| gasTipChanged(currentBlock.GasTip(), header.GasTip())` 추가 + `gasTipChanged` 헬퍼.
   - `core/txpool/legacypool/legacypool.go`: `RemotesBelowTip`이 `tx.GasTipCap()` 대신 `tx.GetAnzeonTipCap()` 사용.
2. **라이브 find_callers는 cks `internal/ckgclient/real.go`** 구현이다. ckg `pkg/mcphandlers`가 아니다. cks-side 브릿지를 항상 검증하라: `grep interfaceMethodSeeds .../code-knowledge-system/internal/ckgclient/real.go`.
3. **B는 인덱스 재빌드 불필요**(implements 엣지는 기존 그래프에 이미 있음). 단 schema 1.15→1.21 호환 위해 이번에 재빌드함.
4. **ckv 포맷은 안 깨짐**(#9 canonical_id는 데이터 추가) — schema 격차는 ckg 문제. 단 scope/sol 일관성 위해 ckv도 재빌드함.
5. **gvm go**: 비대화 셸 PATH 없음 → `zsh -lic`. **GOPRIVATE=github.com/0xmhha/\*** 필수(사설 모듈).
6. **squash-merge 함정**: `git merge-base --is-ancestor`로 "main에 들어갔나" 판정하면 squash로 해시가 달라 오판한다 — 내용(grep)으로 확인하라.
7. **stale cks-mcp 프로세스 누적**: 세션마다 서브프로세스가 남을 수 있음. `pkill -f 'bin/cks-mcp -config .*cks-pr77.yaml'` 후 `/mcp` 재연결.
8. **테스트 파일은 DB 포함**(예시·의도·수정참고). 평소 결과에선 `exclude_tests=true`로 필터(이미 cks 툴 파라미터로 지원).

---

## 9. 빠른 재검증 시퀀스 (이어받자마자)

```
0) (완전 새 머신) §4A 부트스트랩: 레포 클론 + test/pr-77 checkout 0bf2f4d1b
   + ollama/bge-m3 + cks-pr77.yaml + ~/.claude/settings.json + 플러그인 설치
1) 각 레포 git fetch && status (origin 최신 확인; §3 표와 대조)
2) (새 머신) §5.0 바이너리 빌드 + §5 인덱스 재빌드
3) §6 stale 정리 → /mcp reconnect
4) cks_ops_health  → schema 1.21 / ckv reachable / data_path 확인
5) B 스모크: find_callers("gasprice.AnzeonTipEnv.GetAnzeonTipCap", exclude_tests=true)
   → ValidateTransactionWithState 회수되면 B 정상
6) (선택) lean /coding-agent:diagnose 재실행으로 A 정상 확인
→ 모두 OK면 Task #5(full bugfix 라이브 런) 진행
```
