# ADR-0012 — `stablenet-expert:doctor` 스텝 재구성: 공통 환경 체크 + MCP 연결성 체크 + 결정/실행 분리

문서 성격: **ADR / 설계 결정 (Accepted 2026-08-03).**
짝 문서: [ADR-0011](ADR-0011-stablenet-expert-doctor-interactive-setup.md)(직전 결정, 이 ADR이
supersede) · [ADR-0010](ADR-0010-stablenet-expert-meta-plugin-design.md)(메타 플러그인 1단계) ·
`docs/SETUP.md` §1(Prerequisites)/§9.9(MCP 중복 등록) · `commands/doctor.md`(구현 대상).

> **결정 한 줄:** `stablenet-expert:doctor`의 스텝 구조를 ADR-0011의 5단계(체크→보고→자체수정
> 프롬프트→위임 프롬프트→재검증)에서 **0-5 6단계**로 재구성한다 — (0) 플러그인별이 아닌
> 전체-공통 환경 체크, (1) 플러그인 설치 여부, (2) MCP 연결성 체크(신규), (3) 무엇을 고칠지
> **멀티셀렉트로 결정만**, (4) 결정된 것을 **실행**(플러그인별 setup 위임을 이 단계에 흡수), (5)
> MCP 이중 등록 충돌 검증(모든 수정이 끝난 뒤 마지막에 — Step 4의 설치가 새 충돌을 만들 수
> 있으므로). 추가로, MCP 연결 값(URL/IP/토큰)은 **어떤 체크 출력에도 resolve된 값을 찍지
> 않고**, 미설정 시 이 대화 밖에서(사용자가 직접 자기 터미널에서) 환경변수로 설정하도록
> `scripts/set-mcp-env.sh`를 신설한다 — §2.5 참조.
> **상태:** Accepted (구현 완료 — `scripts/check-environment.sh`·`check-mcp-connectivity.sh`·
> `scripts/set-mcp-env.sh` 신규 작성, 기존 `scripts/check-mcp-conflicts.sh`의 HTTP 충돌 보고에서
> resolve된 URL 출력 제거, `commands/doctor.md` 전면 재작성, `scripts/check-setup-delegates.sh`
> 제거·Step 4에 인라인 흡수)

---

## 1. Context (왜)

ADR-0011은 `midnight-expert:doctor`의 Step 1(자체 체크와 병렬로 Tooling 위임 여부를 물음)/Step
4(Offer Fixes)/Step 5(재검증) 패턴을 그대로 가져와 5단계로 설계했다. 실제 사용(2026-08-03,
`/stablenet-expert:doctor` 첫 라이브 실행 후 사용자 피드백)에서 다음 네 가지 구조적 문제가
드러났다:

1. **환경 체크가 아예 없었다.** ADR-0010/0011은 "플러그인 설치 여부"와 "MCP 이중 등록"만
   체크했지, `docs/SETUP.md` §1의 Go/C toolchain/Node/git/gh/Ollama+bge-m3 같은 **공통 툴체인
   전제 조건**은 아무도 체크하지 않았다. 사용자는 처음에 "플러그인별로 필요한 요소를 나눠서
   체크"하는 안을 검토했으나, 최종적으로는 **플러그인 단위로 쪼개지 않고 마켓플레이스 전체가
   공통으로 필요로 하는 요소를 하나의 평평한 목록**으로 체크하는 쪽으로 확정했다 — 이 목록은
   이미 `docs/SETUP.md` §1에 존재하는 표와 동일하므로 새로 설계할 필요가 없었다.
2. **MCP "연결" 자체를 아무도 검증하지 않았다.** ADR-0011까지의 `check-mcp-conflicts.sh`는
   "두 플러그인이 같은 서버를 등록했는가"만 보지, "그 서버가 실제로 설정돼 있고(env 채워짐)
   도달 가능한가"는 별개 질문인데 체크가 없었다. 이번 라이브 실행에서 실제로
   `JIRA_API_TOKEN`이 `CHANGE-ME` 플레이스홀더로 남아있는 상태가 있었고, 기존 체크로는
   탐지되지 않았다.
3. **"수정 여부를 결정하는 것"과 "실제로 설치를 실행하는 것"이 분리돼 있지 않았다.** ADR-0011
   §2.1은 이슈마다 개별 `AskUserQuestion`으로 하나씩 순차 확인했다. 사용자는 여러 개를
   한번에 멀티셀렉트(체크박스)로 골라서 진행하고 싶어했다 — 순차 예/아니오 프롬프트 여러 번이
   아니라, "무엇을 고칠지" 한 번에 결정하고 그다음에 실행하는 2단계로 나눠야 한다는 것.
4. **플러그인별 setup 위임이 별도 최종 스텝으로 분리돼 있던 것이 부자연스러웠다.** ADR-0011
   §2.2는 위임을 체크 리포트 다음의 독립된 스텝으로 뒀다. 사용자는 위임이 "그 플러그인을
   설치/활성화하는 실행 단계"의 일부여야 한다고 판단했다 — 플러그인을 하나 설치·활성화할 때
   그 자리에서 그 플러그인의 setup도 같이 처리하는 게 자연스럽지, 전체 플러그인을 다 처리한
   뒤에 다시 한 바퀴 도는 것은 불필요한 간접화였다.

5. **MCP 연결 값(URL/IP/토큰)이 대화 컨텍스트로 새고 있었다.** Step 2 스크립트의 첫 구현은
   `${STABLENET_KNOWLEDGE_MCP_URL}`을 resolve한 실제 값(사설 IP 포함)을 그대로 한 줄에 찍었다.
   이 출력은 Bash 툴 결과로 LLM 컨텍스트에 그대로 들어간다 — `doctor`를 실행할 때마다 내부
   서버 주소가 매번 대화에 노출되는 셈이었다. 저장소의 `.mcp.json` 자체는 이미 `${VAR}` 참조만
   쓰고 있어 git에는 안전했지만(§1의 다른 문제들과 달리 "커밋된 값"의 문제가 아니라 "런타임에
   체크 스크립트가 출력하는 값"의 문제), 사용자는 이걸 짚으며 "IP 주소는 github에서 절대
   관리하면 안 되고, 게다가 LLM에 전달되는 것 자체도 문제"라고 정정했다. 같은 이유로, 미설정된
   값을 채우는 방법도 `AskUserQuestion`에 직접 입력받거나 doctor가 대신 파일을 쓰는 방식이면
   안 된다 — 그 값을 doctor(=LLM)가 한 번이라도 보게 되기 때문. §2.5에서 이 두 가지(출력
   비노출 + 대화 밖 설정 채널)를 함께 다룬다.

추가로, 이 세션 중 사용자가 ADR-0011/`docs/SETUP.md` §9.9의 MCP 충돌 설명("플러그인들이 같은
mcp를 사용하지 못하기 때문")이 부정확하다고 지적했다 — 하나의 MCP 서버가 다수의 클라이언트
연결을 동시에 받는 것은 흔한 일이다. 공식 문서(`https://code.claude.com/docs/en/mcp.md`,
"Scope hierarchy and precedence") 재조사 결과, 실제 메커니즘은 **Claude Code가 MCP 서버
선언을 이름이 아니라 resolve된 엔드포인트(URL 또는 stdio 커맨드+args) 기준으로 중복 제거**하고,
동일 엔드포인트로 resolve되는 선언이 둘 이상이면 **local > project > user > plugin-provided >
connector** 순위에서 가장 높은 것 하나만 연결된다는 것이었다. 이 설명이 `docs/SETUP.md` §9.9와
새 Step 5 서술에 반영됐다(이 ADR의 범위에 포함, 별도 ADR 불필요 — 기존 결정의 서술 정정이지
새로운 아키텍처 결정이 아님).

## 2. Decision (무엇)

`commands/doctor.md`를 다음 6단계로 재작성한다:

- **Step 0 — 공통 환경 체크** (`scripts/check-environment.sh`, 신규): Go≥1.25/C
  toolchain/Node≥18/git≥2.40/gh≥2.50/python3/Ollama+bge-m3를 `docs/SETUP.md` §1과 동일한
  평평한 목록으로, 어떤 플러그인이 설치돼 있는지와 무관하게 무조건 체크한다.
- **Step 1 — 플러그인 설치 여부** (`scripts/check-plugins.sh`, 기존 그대로): ADR-0010에서
  변경 없음.
- **Step 2 — MCP 연결성 체크** (`scripts/check-mcp-connectivity.sh`, 신규): 활성화된 각
  플러그인이 선언한 MCP 서버마다 (a) 필요한 env가 채워져 있고 `CHANGE-ME` 플레이스홀더가
  아닌지, (b) 실제로 도달 가능한지(HTTP는 2초 타임아웃 GET 프로브, stdio는 바이너리
  존재+실행권한)를 확인한다. `check-mcp-conflicts.sh`(Step 5)와는 독립적인 질문이다 — 완벽히
  설정·도달 가능한 서버라도 다른 플러그인과 중복 등록될 수 있다.
- **Step 3 — 무엇을 고칠지 결정** (`AskUserQuestion`, `multiSelect: true` 하나로): Step
  0-2의 non-pass 항목을 전부 체크박스 옵션으로 모아 한 번에 묻는다. 이 단계는 **결정만** —
  아무것도 설치/변경하지 않는다. Step 5의 MCP 충돌 항목은 여기 포함하지 않는다(Step 4의
  설치가 새 충돌을 만들 수 있어 Step 3 시점엔 정확히 평가할 수 없음).
- **Step 4 — 선택된 것 실행**: 종류별로 다르게 처리한다 — 플러그인 설치/활성화와
  `ollama pull bge-m3`는 안전/가역적이라 직접 실행, 그 외 툴체인 설치(시스템 패키지 매니저)는
  플랫폼별 명령만 안내하고 직접 실행하지 않음(비가역적 시스템 변경이라 별도 확인 없이 일괄
  처리하면 안 됨), MCP env 미설정은 값을 대신 채우지 않고 어느 파일의 어느 키를 고칠지만
  안내. **플러그인을 설치/활성화하는 바로 그 자리에서** 그 플러그인이 `commands/setup.md`를
  갖고 있으면 위임 여부를 묻는다(ADR-0011 §2.2의 위임 원칙은 유지, 실행 시점만 이동) —
  전체 플러그인을 다시 순회하는 별도 스텝이 아니라 플러그인 단위 처리에 인라인.
- **Step 5 — MCP 이중 등록 충돌 검증** (`scripts/check-mcp-conflicts.sh`, 기존 로직 그대로,
  서술만 정정): Step 4의 수정이 끝난 뒤 마지막에 실행한다. 충돌 설명을 "서버가 여러 플러그인을
  처리 못해서"가 아니라 "Claude Code의 엔드포인트 기준 중복 제거 + 우선순위(local > project >
  user > plugin > connector)에서 동순위 충돌"로 정정한다.

### 2.5 MCP 연결 값은 대화에 절대 노출하지 않는다

`check-mcp-connectivity.sh`(Step 2, 신규)는 `${VAR}`를 resolve한 뒤에도 그 결과 값(URL/IP/토큰)을
**절대 출력하지 않는다** — 대신 `"reachable (configured via STABLENET_KNOWLEDGE_MCP_URL)"`처럼
참조하는 env var **이름**만 출력한다. HTTP 연결 실패 시의 예외 메시지도 그대로 찍지 않는다
(`URLError`/`OSError` 메시지에 resolve된 host/IP가 섞여 나오는 경우가 흔해서, 실패 사유만 일반화해
보고한다). **기존** `check-mcp-conflicts.sh`(Step 5, ADR-0010부터 있던 스크립트)도 같은 문제가
있었다 — HTTP 충돌을 보고할 때 resolve된 URL을 그대로 찍고 있었다(라이브 검증 중
`http://172.20.242.13:8930/mcp`가 실제로 출력되는 것을 확인). 이 ADR에서 함께 고쳐, HTTP 충돌은
이제 "어느 env var를 통해 설정됐는지"만 나열하고(예: `coding-agent:cks (via CKS_MCP_URL),
core-dev:stablenet-knowledge (via STABLENET_KNOWLEDGE_MCP_URL)`) resolve된 URL 자체는 내부
충돌 탐지에만 쓰고 출력하지 않는다. stdio 충돌(로컬 바이너리 경로)은 네트워크 주소가 아니므로
계속 경로를 그대로 보여준다. `doctor.md`도 이 원칙을 명시한다: 체크 스크립트 출력을 그대로
전달할 것, 스스로 env var를 resolve해서 "친절하게" 값을 대화에 풀어 쓰지 말 것.

값이 없거나(`missing`) 플레이스홀더(`CHANGE-ME`)인 경우, doctor는 **값을 직접 받거나 대신
써주지 않는다** — `AskUserQuestion`으로 값을 입력받는 것도, doctor가 Bash로 파일에 값을 쓰는
것도 모두 그 값이 최소 한 번은 이 대화(=LLM 컨텍스트)를 거치게 만든다. 대신 신규
`scripts/set-mcp-env.sh <VAR_NAME> [--scope user|project]`를 만든다 — `read -s`(터미널에
에코되지 않는 히든 입력)로 값을 받아 `~/.claude/settings.json`(또는 프로젝트 스코프면 이미
gitignore된 `.claude/settings.local.json`)의 `env` 맵에 직접 쓰고, 자기 출력에도 값을 절대
echo하지 않는다. `doctor.md`는 이 스크립트를 **사용자가 자기 터미널에서 직접 실행**하도록
안내만 하고, 절대 Bash 툴로 대신 실행하지 않는다 — 대신 실행하면 그 프롬프트/stdin/stdout이
결국 같은 대화로 돌아오기 때문에 우회 채널을 만든 의미가 없어진다. 이렇게 하면 사용자가 원했던
"연결 안 됐을 때 입력할 수 있는 입력란"이 존재하면서도(=`read -s` 프롬프트), 그 입력이 LLM에
전달되는 문제는 생기지 않는다(=대화 밖 별도 프로세스).

부수 변경: `scripts/check-setup-delegates.sh`를 삭제한다 — 이 스크립트가 모으던 정보(플러그인이
`commands/setup.md`를 갖고 있는가)는 이제 Step 4에서 처리 대상 플러그인마다 그 자리에서 직접
`Read`로 확인하므로, 전체 플러그인을 미리 훑어 별도 리포트 섹션을 만드는 독립 스텝 자체가
없어졌고 스크립트를 유지할 이유가 없다.

## 3. Consequences (결과)

- **+**: 공통 툴체인 누락(Go/Node/gh 등)이 마켓플레이스 진입 시점에 바로 드러난다 — 기존에는
  개별 플러그인의 명령을 실행하다 실패해야 알 수 있었다.
- **+**: MCP env 미설정(`CHANGE-ME` 플레이스홀더 등)을 doctor가 직접 잡아낸다 — 실제로
  `JIRA_API_TOKEN`이 이 상태였던 걸 이번 라이브 실행에서 확인.
- **+**: 결정(Step 3)과 실행(Step 4)의 분리로 여러 항목을 한 번에 검토·승인할 수 있다 — 이슈
  개수만큼 순차 프롬프트를 반복하지 않는다.
- **+**: MCP 충돌 검증(Step 5)을 모든 수정 뒤로 미룸으로써, Step 4에서 새로 설치한 플러그인이
  만드는 충돌까지 같은 세션에서 잡아낸다(이전 순서였다면 Step 4 격의 위임 스텝 전에 충돌
  체크가 끝나 있어 놓쳤을 케이스).
- **−/제약**: Step 4에서 시스템 툴체인 설치는 명령만 안내하고 자동 실행하지 않는다 — 사용자가
  안내받은 명령을 직접 실행해야 하며, doctor가 "설치 완료"로 자동 확인해주지 않는다(의도된
  제약, 비가역적 시스템 변경이라 별도 동의 없이 일괄 처리 대상이 아님).
- **+**: MCP 연결 값(URL/IP/토큰)이 체크 실행마다 대화 컨텍스트로 새던 문제가 사라진다 —
  `check-mcp-connectivity.sh`는 이제 env var 이름만 보고하고, 값 설정도 `set-mcp-env.sh`를 통해
  대화 밖에서 이뤄진다.
- **−/제약**: `set-mcp-env.sh`는 `.mcp.json`이 `${VAR}` 참조를 쓰는 경우에만 작동한다 — 값을
  하드코딩한 플러그인은 이 메커니즘의 보호를 받지 못한다(§1 다섯 번째 항목의 한계, 코드 수정
  필요).
- **후속**: `docs/adr/README.md` 인덱스에 이 ADR 추가, ADR-0011 상태를 `Superseded by
  ADR-0012`로 갱신(§4 참조).
