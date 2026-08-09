# ADR-0019 — doctor 체크의 마켓플레이스 스코프: 보고 범위와 수정 범위를 분리한다

문서 성격: **ADR / 설계 결정 (Accepted 2026-08-09).**
짝 문서: `plugins/stablenet-expert/commands/doctor.md`,
`plugins/stablenet-expert/scripts/check-mcp-connectivity.sh`,
`plugins/stablenet-expert/scripts/check-mcp-conflicts.sh`,
`plugins/stablenet-expert/scripts/tests/test_check_mcp.py`

> **결정 한 줄:** MCP 체크는 모든 마켓플레이스의 활성 플러그인을 계속 넓게 스캔하되, 이
> 마켓플레이스 소유가 아닌 플러그인의 문제는 `critical`이 아니라 새 상태 `external`로 보고하고
> Step 3/Step 5의 수정 선택지에서 제외한다.
> **상태:** Accepted (구현 반영됨)

## 1. Context (왜)

`/stablenet-expert:doctor` 실행 시, 이 마켓플레이스와 무관한 `coding-agent` 플러그인의 MCP 서버
3개(`jira-gateway`·`cks`·`chainbench`) 환경설정을 사용자에게 물었다. 2026-08-09 라이브에서 관측됐고
재현했다.

원인은 하드코딩이 아니다. `check-mcp-connectivity.sh`는 플러그인 이름을 조회하지 않고
`~/.claude/settings.json`의 `enabledPlugins` **전체**를 순회하며, `.mcp.json`이 있는 모든 항목을
검사한다(마켓플레이스 구분 없음). 사용자 머신에 `stablenet-expert` 이전 단계인
`coding-agent@coding-agent`가 비활성화되지 않은 채 남아 있었고, 그 `.mcp.json`의 env가 미설정이라
`critical` 3행이 방출됐다. `doctor.md` Step 3이 "Steps 0-2의 모든 non-`pass` 행"을 멀티셀렉트로
모으므로 그대로 체크박스가 됐다.

문제는 그 체크박스에 **뒤가 없다는 것**이다. Step 4의 위임은 `"every enabled plugin of this
marketplace"`로 명시적으로 좁혀져 있고, 외부 플러그인은 ADR-0014의 `scripts/setup.py`를 싣지
않는다. 즉 선택해도 doctor가 수행할 동작이 없다. ADR-0011 §2.2("플러그인 자신의 env 지식은 그
플러그인 소유")를 스코프 측면에서 위반한 셈이다 — 남의 마켓플레이스 설정을 우리 doctor가 쓰겠다고
제안한 것이다.

넓은 스캔 자체는 의도된 것이며 유지해야 한다. ADR-0010의 근거 사례가 정확히 "외부 플러그인
(`coding-agent`)이 우리 플러그인(`core-dev`)의 MCP 서버를 조용히 끊는" 충돌이었다. 스캔을 좁히면
그 탐지 능력을 잃는다.

## 2. Decision (무엇)

**보고 범위(넓게)와 수정 범위(좁게)를 분리하고, 그 경계를 행 상태로 표현한다.**

소유 판정은 레지스트리 키 형식 `<plugin>@<marketplace>`의 마켓플레이스 부분으로 한다. 별도의
marketplace.json 읽기가 필요 없고, 나중에 추가될 플러그인에도 그대로 맞는다.

1. **새 상태 `external`.** 기존 `pass`/`info`/`warn`/`critical`에 추가한다. 외부 마켓플레이스
   플러그인의 문제 행은 `external`로 방출하며, 진단 내용(미설정 변수명 등)은 그대로 싣는다 —
   행동 가능성만 낮추고 진단은 낮추지 않는다. ADR-0012의 값 비노출 규칙은 그대로 적용된다.

   `info`를 재사용하지 않은 이유: `info`는 이미 **행동 가능한** 항목에도 쓰인다
   (`check-plugins.sh`의 `not installed (install only what you need)`). 상태값만으로
   행동 가능성을 판정하려면 전용 값이 필요하다.

2. **판정(verdict)은 자기 소유 서버만 센다.** `ALL_MCP_CONNECTIVITY_PASS`는 이 마켓플레이스
   서버 기준으로 방출되며 `external` 행과 공존할 수 있다. 그렇지 않으면 무관한 잔여 플러그인
   하나가 이 생태계를 영구히 "실패" 상태로 묶어두는데, 그 실패는 여기서 제공하는 어떤 수정으로도
   해소할 수 없다.

3. **충돌은 우리 플러그인이 당사자일 때만 `critical`.** 외부끼리의 충돌은 `external`로 보고만
   한다. Step 5의 구제책이 "둘 중 하나를 `enabledPlugins`에서 비활성화"인데, 양쪽 다 외부면 그건
   우리가 소유하지 않은 플러그인을 우리 doctor가 끄는 행위가 된다. 혼합 충돌(우리+외부)은
   `critical`을 유지한다 — ADR-0010의 근거 사례이며, 우리 플러그인이 피해자이므로 범위 안이다.

4. **Step 3의 "actionable" 정의를 명문화한다.** `non-pass` → `non-pass AND non-external`.
   `external` 행은 최종 보고의 *Left as-is*에만 나타난다.

### 대안과 trade-off

- *외부 행을 아예 방출하지 않는다* — 더 단순하지만 진단을 잃는다. 사용자가 "왜 이 MCP가 안 붙지"를
  물을 때 doctor가 침묵하게 된다. 이 저장소의 "say so if relevant, don't silently omit" 원칙과도
  어긋난다. 기각.
- *행 포맷에 4번째 필드(소유 여부)를 추가* — 세 스크립트가 공유하는 `name | status | detail`
  계약을 깬다. 기각.
- *스캔을 우리 마켓플레이스로 좁힌다* — ADR-0010의 교차 마켓플레이스 충돌 탐지를 잃는다. 기각.

## 3. Consequences (결과)

- 잔여/무관 플러그인이 있어도 doctor의 판정과 질문이 이 생태계 범위에 머문다. 관측된 증상
  (`coding-agent MCP` 탭)이 사라진다.
- 교차 마켓플레이스 충돌 탐지(ADR-0010의 핵심 가치)는 그대로 유지된다.
- `external`은 doctor가 소비하는 새 상태다. 이후 체크 스크립트를 추가할 때 같은 규칙을 따라야
  한다 — 외부 소유 대상의 문제는 `critical`이 아니다.
- 검증: `plugins/stablenet-expert/scripts/tests/test_check_mcp.py` 12건이 계약을 고정한다.
  회귀 방지 불변식(우리 플러그인은 여전히 `critical`, 비활성 플러그인은 미보고, 해석된 값 비노출,
  혼합 충돌은 `critical`)을 함께 고정했다. CI의 `python-tests` 잡이 `plugins/*/scripts/tests`를
  자동 탐색하므로 워크플로 수정은 불필요하다.
- 이 마켓플레이스의 플러그인이 아직 하나도 설치되지 않은 상태에서 Step 2는
  `no enabled stablenet-expert plugin registers any MCP server`를 보고한다(이전 문구는 마켓플레이스
  언급이 없어, 외부 서버가 존재할 때 사실과 어긋났다).
