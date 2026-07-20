---
name: template-parse
description: "Jira 티켓 템플릿 파싱. 작업 유형(Feature/Bug Fix/Code Review/Release) 식별 + 필드 구조화 + 파이프라인 분기 결정."
type: skill
---

# Template Parse

Jira 티켓의 description(markdown)을 파싱하여 작업 유형을 식별하고 필드를 구조화한다.

이 skill은 LLM이 markdown 텍스트를 의미적으로 파싱한다. 단순 regex만으로는 한글/영문 변형, 들여쓰기 변형, 추가 텍스트 등을 다루기 어렵기 때문에 LLM의 텍스트 이해 능력을 활용한다.

---

## 1. 입력

- `description` (string): Jira 티켓의 description 본문 (markdown)
  - Jira API v3에서 받은 ADF가 markdown으로 변환된 형태 (RI-04 참조)
- `summary` (string, optional): Jira 티켓의 summary 필드. 본문에 요약이 없을 때 폴백.

## 2. 출력

```jsonc
{
  "work_type": "feature" | "bugfix" | "code_review" | "release" | "unknown",
  "summary": "한 줄 요약",
  "pipeline_variant": "full" | "review_only" | "release",
  "missing_fields": ["..."],
  "fields": {
    // work_type별 다른 필드 구조 (아래 섹션 5 참조)
  },
  "warnings": ["..."]
}
```

---

## 3. 절차

### 3.1 작업 유형 식별

description 본문에서 다음 패턴을 탐색한다 (대소문자 무관):

```
"## 작업 유형:" 또는 "## Work Type:"
"## 타입:" 또는 "## Type:"
"**작업 유형**:" (인라인 강조)
```

값 추출 후 다음으로 매핑:

| 값 (한글/영문) | work_type |
|---------------|-----------|
| Feature, 기능, 기능 추가, New Feature, Enhancement | `feature` |
| Bug Fix, Bug, 버그, 버그 수정, Fix, Defect | `bugfix` |
| Code Review, Review, 코드 리뷰, 리뷰 | `code_review` |
| Release, 릴리즈, 릴리스, Version, 버전 | `release` |

명시적 작업 유형 라인이 없는 경우, **summary와 description 본문 내용**으로 추론:
- "fix", "bug", "에러", "버그", "수정" 키워드 다수 → `bugfix`
- "review", "리뷰", "검토" → `code_review`
- "v1.", "release", "릴리즈", "태그" → `release`
- 위 모두 해당 없음 + 새 기능 설명 → `feature`
- 추론 불가능 → `"unknown"` + warning 추가

### 3.2 섹션 파싱

description 본문을 `## ` 또는 `### ` 헤더 기준으로 섹션 분할.

각 섹션의 헤더를 다음 표로 정규화:

| 헤더 패턴 (한글/영문, 대소문자/공백 무관) | 정규화된 키 |
|--------------------------------------------|------------|
| 요약, Summary, Overview, TL;DR | `summary` |
| 배경, Background, Context, Motivation | `background` |
| 요구사항, Requirements, 요구 사항 | `requirements` |
| 영향 범위, Scope, Impact, 범위 | `scope` |
| 수용 기준, Acceptance Criteria, AC, 인수 조건 | `acceptance_criteria` |
| 참고 자료, References, 참고, Links | `references` |
| 재현 방법, Steps to Reproduce, 재현 단계, Repro | `steps_to_reproduce` |
| 기대 동작, Expected Behavior, Expected | `expected` |
| 실제 동작, Actual Behavior, Actual | `actual` |
| 리뷰 대상, Review Target, Target | `review_target` |
| 리뷰 기준, Review Criteria, Criteria | `review_criteria` |
| 버전, Version | `version` |
| 포함 변경사항, Changes, Included Changes | `changes` |
| 릴리즈 체크리스트, Release Checklist, Checklist | `checklist` |
| 심각도, Severity | `severity` |

### 3.3 필드 값 추출

각 섹션의 본문에서 다음 패턴을 추출:

**체크리스트 (배열)**:
```
- [ ] 항목 A
- [x] 항목 B (체크됨)
- [ ] 항목 C
```
→ `[{ "text": "항목 A", "checked": false }, { "text": "항목 B", "checked": true }, ...]`

**불릿 리스트 (배열)**:
```
- 항목 1
- 항목 2
* 항목 3
```
→ `["항목 1", "항목 2", "항목 3"]`

**키-값 라인** (영향 범위 등):
```
- 모듈: consensus, governance
- 예상 변경 파일: consensus/wbft/finalize.go
- 심각도: high
```
→ `{ "modules": ["consensus", "governance"], "expected_files": ["..."], "severity": "high" }`

**일반 텍스트 (문자열)**:
헤더 다음의 연속된 텍스트 단락.

---

## 4. 파이프라인 분기 결정

| work_type | pipeline_variant |
|-----------|------------------|
| feature | `full` |
| bugfix | `full` |
| code_review | `review_only` |
| release | `release` |
| unknown | `full` (기본값, warning 포함) |

---

## 5. work_type별 필드 구조

### 5.1 feature

```jsonc
{
  "work_type": "feature",
  "summary": "...",
  "pipeline_variant": "full",
  "fields": {
    "summary": "한 줄 요약",
    "background": "왜 필요한지",
    "requirements": [{ "text": "...", "checked": false }],
    "scope": {
      "modules": ["consensus"],
      "expected_files": ["consensus/wbft/finalize.go"]
    },
    "acceptance_criteria": [{ "text": "...", "checked": false }],
    "references": "관련 링크/문서"
  },
  "missing_fields": []
}
```

**필수 필드**: summary, requirements (또는 background), scope.modules

### 5.2 bugfix

```jsonc
{
  "work_type": "bugfix",
  "summary": "...",
  "pipeline_variant": "full",
  "fields": {
    "summary": "한 줄 요약",
    "steps_to_reproduce": ["단계 1", "단계 2"],
    "expected": "정상 동작",
    "actual": "현재 동작",
    "scope": {
      "modules": ["consensus"],
      "severity": "high"
    },
    "acceptance_criteria": [{ "text": "...", "checked": false }]
  },
  "missing_fields": []
}
```

**필수 필드**: summary, steps_to_reproduce, expected, actual, scope.modules

### 5.3 code_review

```jsonc
{
  "work_type": "code_review",
  "summary": "...",
  "pipeline_variant": "review_only",
  "fields": {
    "summary": "리뷰 대상 및 목적",
    "review_target": {
      "files_or_modules": ["consensus/wbft/"],
      "perspective": "성능 / 보안 / 아키텍처 / 정확성"
    },
    "review_criteria": ["..."]
  },
  "missing_fields": []
}
```

**필수 필드**: summary, review_target.files_or_modules

### 5.4 release

```jsonc
{
  "work_type": "release",
  "summary": "...",
  "pipeline_variant": "release",
  "fields": {
    "version": "v1.2.3",
    "changes": [
      { "ticket": "STABLE-1230", "summary": "..." },
      { "ticket": "STABLE-1231", "summary": "..." }
    ],
    "checklist": [{ "text": "...", "checked": false }]
  },
  "missing_fields": []
}
```

**필수 필드**: version, changes

---

## 6. 검증

### 6.1 필수 필드 누락 체크

각 work_type별 "필수 필드"를 검증:
- 필드가 없거나 빈 값이면 `missing_fields` 배열에 필드 경로 추가
  - 예: `"missing_fields": ["scope.modules", "acceptance_criteria"]`

### 6.2 경고 (warnings)

다음 상황에서 warning 추가:
- work_type이 "unknown"으로 추론된 경우: `"작업 유형이 명시되지 않아 'feature'로 추정합니다"`
- pipeline_variant가 "review_only"인데 acceptance_criteria가 명시된 경우: 모순
- release인데 ChainBench 체크리스트가 누락된 경우

### 6.3 missing_fields가 있는 경우의 동작

- **필수 필드 누락 시에도 작업은 진행** (pipeline_variant는 결정)
- 다만 Orchestrator/Planner가 missing_fields를 받으면:
  - 누락 필드를 유저에게 알리고 추가 정보 요청
  - 또는 Jira 코멘트로 보강 요청
  - 보강 없이 진행 시 ANALYSIS 단계에서 LLM이 추론

---

## 7. 사용 예시

### 입력 예시
```markdown
## 작업 유형: 버그 수정

## 요약
WBFT consensus의 Finalize 함수에서 nil pointer 발생

## 재현 방법
1. 4노드 로컬 네트워크 시작
2. gov_validator 미설정 상태에서 블록 생성

## 기대 동작
gov_validator이 없으면 graceful skip

## 실제 동작
panic: nil pointer dereference at consensus/wbft/finalize.go:89

## 영향 범위
- 모듈: consensus
- 심각도: high

## 수용 기준
- [ ] nil guard 추가
- [ ] unit test 추가
- [ ] race test 통과
```

### 출력 예시
```jsonc
{
  "work_type": "bugfix",
  "summary": "WBFT consensus의 Finalize 함수에서 nil pointer 발생",
  "pipeline_variant": "full",
  "fields": {
    "summary": "WBFT consensus의 Finalize 함수에서 nil pointer 발생",
    "steps_to_reproduce": [
      "4노드 로컬 네트워크 시작",
      "gov_validator 미설정 상태에서 블록 생성"
    ],
    "expected": "gov_validator이 없으면 graceful skip",
    "actual": "panic: nil pointer dereference at consensus/wbft/finalize.go:89",
    "scope": {
      "modules": ["consensus"],
      "severity": "high"
    },
    "acceptance_criteria": [
      { "text": "nil guard 추가", "checked": false },
      { "text": "unit test 추가", "checked": false },
      { "text": "race test 통과", "checked": false }
    ]
  },
  "missing_fields": [],
  "warnings": []
}
```

---

## 8. ADF (Atlassian Document Format) 처리 (RI-04)

Jira Gateway MCP가 ADF → markdown 변환을 처리한 후 이 skill을 호출하는 것이 원칙이다.

만약 description이 ADF JSON 형태로 전달되면:
1. Jira Gateway MCP의 ADF 변환기로 markdown 변환을 먼저 수행
2. 또는, 이 skill 내에서 ADF의 `text` 노드들을 순회하여 평문 추출

ADF 변환은 Phase 2 (Jira Gateway MCP)의 책임이므로, 이 skill은 markdown 입력을 가정한다.
