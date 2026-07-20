# Phase 2: Jira Gateway MCP + Sensitive Filter

> Atlassian MCP 앞단의 프록시 MCP 서버.
> 모든 Jira 읽기 응답에서 민감정보를 LLM 도달 전에 필터링한다.

## 1. 아키텍처

```
Agent(LLM)
    │ MCP tool call
    ▼
┌──────────────────────────────────────┐
│        Jira Gateway MCP Server        │
│                                       │
│  ┌─────────────┐  ┌──────────────┐   │
│  │ Tool Router  │  │  Sensitive   │   │
│  │             │  │  Filter      │   │
│  │ read tools  │──│  Engine      │   │
│  │ → filter    │  │              │   │
│  │ write tools │  │ patterns.json│   │
│  │ → passthru  │  │ entropy calc │   │
│  └──────┬──────┘  └──────────────┘   │
│         │                             │
│  ┌──────▼──────┐                      │
│  │ Atlassian   │                      │
│  │ MCP Client  │                      │
│  │ (upstream)  │                      │
│  └──────┬──────┘                      │
│         │                             │
└─────────┼─────────────────────────────┘
          ▼
    Atlassian MCP Server (기존)
          │
          ▼
       Jira API
```

### 1.1 읽기/쓰기 분리 원칙

| 방향 | 동작 | 필터 |
|------|------|------|
| **읽기** (Jira → Agent) | 티켓 내용, 코멘트, 첨부파일 정보 읽기 | Sensitive Filter **적용** |
| **쓰기** (Agent → Jira) | 댓글 추가, 상태 변경, 라벨 추가 | Passthrough (필터 불필요) |

쓰기에 필터를 적용하지 않는 이유: Agent가 생성하는 데이터(PR URL, 상태 변경)는 민감정보가 아님. 만약 향후 Agent가 코드 스니펫을 댓글에 포함하는 케이스가 생기면, 쓰기 방향에도 필터를 추가할 수 있다.

---

## 2. MCP Server 설계

### 2.1 구현 언어 및 프레임워크

**Go** + `github.com/modelcontextprotocol/go-sdk`

이유:
- cks-mcp(Go)와 동일 툴체인 → 단일 빌드/테스트 명령
- go-stablenet 팀이 Go 개발자라 유지보수 용이
- npm/Node.js 추가 도구체인 불필요
- Go 표준 라이브러리만으로 HTTP/JSON/regex/AST 처리 충분
- Proxy는 Atlassian MCP를 우회하고 Jira REST API를 직접 호출하므로 TypeScript 생태계 의존 불필요

### 2.2 제공 MCP Tools

Gateway가 노출하는 tool은 Atlassian MCP의 tool을 래핑하되, 읽기 tool에 필터를 적용한다.

```
┌─────────────────────────────────────────────────────────┐
│ Gateway Tool              │ Upstream Tool    │ Filter   │
│───────────────────────────│──────────────────│──────────│
│ jira_read_ticket          │ jira_get_issue   │ ✅ 적용  │
│ jira_read_comments        │ jira_get_comments│ ✅ 적용  │
│ jira_search               │ jira_search      │ ✅ 적용  │
│ jira_add_comment          │ jira_add_comment │ ❌ 통과  │
│ jira_update_status        │ jira_transition  │ ❌ 통과  │
│ jira_update_assignee      │ jira_update      │ ❌ 통과  │
└─────────────────────────────────────────────────────────┘
```

### 2.3 Tool 인터페이스 상세

#### jira_read_ticket

```typescript
interface JiraReadTicketInput {
  ticket_id: string;  // e.g., "STABLE-1234"
  fields?: string[];  // 특정 필드만 요청 (기본: 전체)
}

interface JiraReadTicketOutput {
  ticket_id: string;
  type: string;          // "Feature" | "Bug Fix" | "Code Review" | "Release"
  summary: string;
  description: string;   // 필터링된 본문
  assignee: string;
  status: string;
  labels: string[];
  created: string;
  updated: string;
  
  // 템플릿 파싱 결과 (template-parse skill과 연동)
  parsed_template?: {
    work_type: string;
    requirements?: string[];
    scope?: { modules: string[]; files?: string[] };
    acceptance_criteria?: string[];
  };
  
  // 민감정보 필터 메타데이터
  _filter_metadata: {
    scan_result: "CLEAN" | "REDACTED" | "BLOCKED";
    redacted_count: number;       // [REDACTED]로 치환된 횟수
    redacted_patterns: string[];  // 탐지된 패턴 ID 목록 (값은 노출 안 됨)
    scanned_at: string;
  };
}
```

#### jira_read_comments

```typescript
interface JiraReadCommentsInput {
  ticket_id: string;
  since?: string;  // ISO datetime - 이 시점 이후 코멘트만
}

interface JiraReadCommentsOutput {
  ticket_id: string;
  comments: Array<{
    id: string;
    author: string;
    body: string;       // 필터링된 내용
    created: string;
    updated: string;
  }>;
  _filter_metadata: FilterMetadata;
}
```

#### jira_add_comment (passthrough)

```typescript
interface JiraAddCommentInput {
  ticket_id: string;
  body: string;
}

// Atlassian MCP에 그대로 전달, 응답도 그대로 반환
```

#### jira_update_status

```typescript
interface JiraUpdateStatusInput {
  ticket_id: string;
  status: "In Progress" | "In Review" | "Done" | "Complete";
}
```

---

## 3. Sensitive Filter Engine

### 3.1 아키텍처

```
┌────────────────────────────────────────┐
│         Sensitive Filter Engine         │
│                                         │
│  Input: raw text (Jira 응답 본문)       │
│                                         │
│  ┌──────────────────┐                   │
│  │ 1. Pattern Scan  │                   │
│  │    regex 매칭     │                   │
│  │    (patterns.json)│                   │
│  └────────┬─────────┘                   │
│           ▼                             │
│  ┌──────────────────┐                   │
│  │ 2. Entropy Scan  │                   │
│  │    Shannon entropy│                   │
│  │    고랜덤 문자열  │                   │
│  └────────┬─────────┘                   │
│           ▼                             │
│  ┌──────────────────┐                   │
│  │ 3. Decision      │                   │
│  │                   │                   │
│  │ critical 탐지     │                   │
│  │  → severity에 따라│                   │
│  │    BLOCK 또는     │                   │
│  │    REDACT         │                   │
│  │                   │                   │
│  │ warning만 탐지    │                   │
│  │  → REDACT + 경고  │                   │
│  │                   │                   │
│  │ 미탐지 → CLEAN    │                   │
│  └──────────────────┘                   │
│                                         │
│  Output: filtered text + metadata       │
└────────────────────────────────────────┘
```

### 3.2 patterns.json 전체 정의

```jsonc
{
  "version": "1.0.0",
  "patterns": [
    // === Critical: 즉시 차단 ===
    {
      "id": "private_key_pem",
      "name": "PEM Private Key",
      "regex": "-----BEGIN\\s+(RSA|EC|OPENSSH|DSA|ENCRYPTED)?\\s*PRIVATE KEY-----",
      "severity": "critical",
      "action": "block",
      "description": "PEM 형식 개인 키"
    },
    {
      "id": "aws_access_key",
      "name": "AWS Access Key ID",
      "regex": "AKIA[0-9A-Z]{16}",
      "severity": "critical",
      "action": "redact"
    },
    {
      "id": "aws_secret_key",
      "name": "AWS Secret Access Key",
      "regex": "(?i)aws_secret_access_key\\s*[=:]\\s*[A-Za-z0-9/+=]{40}",
      "severity": "critical",
      "action": "redact"
    },
    {
      "id": "gcp_service_account",
      "name": "GCP Service Account Key",
      "regex": "\"type\"\\s*:\\s*\"service_account\"",
      "severity": "critical",
      "action": "block",
      "description": "GCP 서비스 계정 JSON 전체가 포함된 것으로 판단"
    },
    {
      "id": "openai_api_key",
      "name": "OpenAI API Key",
      "regex": "sk-[a-zA-Z0-9]{20,}",
      "severity": "critical",
      "action": "redact"
    },
    {
      "id": "anthropic_api_key",
      "name": "Anthropic API Key",
      "regex": "sk-ant-[a-zA-Z0-9-]{20,}",
      "severity": "critical",
      "action": "redact"
    },

    // === High: REDACT 처리 ===
    {
      "id": "db_connection_string",
      "name": "Database Connection String",
      "regex": "(postgres|mysql|mongodb)(\\+srv)?://[^\\s]+:[^\\s]+@[^\\s]+",
      "severity": "high",
      "action": "redact"
    },
    {
      "id": "jwt_token",
      "name": "JWT Token",
      "regex": "eyJ[A-Za-z0-9_-]{10,}\\.eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]+",
      "severity": "high",
      "action": "redact"
    },
    {
      "id": "bearer_token",
      "name": "Bearer Token in Header",
      "regex": "(?i)(authorization|bearer)\\s*[=:]\\s*bearer\\s+[A-Za-z0-9_.-]+",
      "severity": "high",
      "action": "redact"
    },
    {
      "id": "webhook_secret",
      "name": "Webhook Secret",
      "regex": "(?i)(webhook[_-]?secret|x-hub-signature)\\s*[=:]\\s*[A-Za-z0-9_.-]{10,}",
      "severity": "high",
      "action": "redact"
    },
    {
      "id": "password_assignment",
      "name": "Password Assignment",
      "regex": "(?i)(password|passwd|pwd)\\s*[=:]\\s*[\"']?[^\\s\"']{6,}[\"']?",
      "severity": "high",
      "action": "redact"
    },

    // === Medium: REDACT + 경고 ===
    {
      "id": "ip_address_internal",
      "name": "Internal IP Address",
      "regex": "\\b(10\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}|172\\.(1[6-9]|2\\d|3[01])\\.\\d{1,3}\\.\\d{1,3}|192\\.168\\.\\d{1,3}\\.\\d{1,3})\\b",
      "severity": "medium",
      "action": "redact"
    },
    {
      "id": "email_address",
      "name": "Email Address",
      "regex": "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}",
      "severity": "medium",
      "action": "warn",
      "description": "이메일은 context에 따라 민감할 수 있음. 경고만 발생."
    },

    // === Entropy 기반 ===
    {
      "id": "high_entropy_string",
      "name": "High Entropy Secret Candidate",
      "type": "entropy",
      "threshold": 4.5,
      "min_length": 20,
      "max_length": 200,
      "severity": "warning",
      "action": "warn",
      "exclude_patterns": [
        "^[a-f0-9]+$",
        "^[A-Z_]+$",
        "^(https?|ftp)://"
      ],
      "description": "hex hash, 상수, URL 등 오탐 제외"
    }
  ],

  "config": {
    "block_behavior": "abort_with_report",
    "redact_replacement": "[REDACTED:{pattern_id}]",
    "warn_behavior": "pass_with_metadata",
    "max_scan_size_bytes": 1048576
  }
}
```

### 3.3 Shannon Entropy 계산

```
entropy(text):
  freq = character frequency distribution of text
  H = -Σ(p * log2(p)) for each p in freq where p > 0
  return H

scan_entropy(text):
  tokens = split text by whitespace and delimiters
  for each token:
    if token.length < min_length or token.length > max_length:
      continue
    if matches any exclude_pattern:
      continue
    if entropy(token) > threshold:
      yield { token, entropy_score, position }
```

### 3.4 REDACT 처리

```
redact(text, matches):
  for each match in matches (sorted by position descending):
    replacement = config.redact_replacement
      .replace("{pattern_id}", match.pattern_id)
    text = text[:match.start] + replacement + text[:match.end]
  return text

예시:
  Input:  "DB 접속: postgres://admin:s3cret@10.0.1.5:5432/prod"
  Output: "DB 접속: [REDACTED:db_connection_string]"
```

### 3.5 BLOCK 처리

critical severity + action:block인 패턴 탐지 시:

```
1. 전체 응답을 LLM에 전달하지 않음
2. 대신 에러 응답 반환:
   {
     "error": "SENSITIVE_CONTENT_BLOCKED",
     "message": "Jira 티켓에 민감정보가 포함되어 있어 처리할 수 없습니다.",
     "detected_patterns": ["private_key_pem"],
     "recommendation": "Jira 티켓에서 해당 민감정보를 제거한 후 다시 시도하세요."
   }
3. logs/sensitive-block-{timestamp}.log에 상세 기록
```

---

## 4. Gateway MCP Server 구현 설계

### 4.1 프로젝트 구조

```
tools/jira-gateway-mcp/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts              # MCP server 진입점
│   ├── server.ts             # MCP server 설정 + tool 등록
│   ├── tools/
│   │   ├── read-ticket.ts    # jira_read_ticket 구현
│   │   ├── read-comments.ts  # jira_read_comments 구현
│   │   ├── search.ts         # jira_search 구현
│   │   ├── add-comment.ts    # jira_add_comment (passthrough)
│   │   ├── update-status.ts  # jira_update_status (passthrough)
│   │   └── update-assignee.ts
│   ├── filter/
│   │   ├── engine.ts         # Sensitive Filter Engine
│   │   ├── patterns.ts       # patterns.json 로더 + 매처
│   │   ├── entropy.ts        # Shannon entropy 계산
│   │   └── redactor.ts       # REDACT/BLOCK 처리
│   ├── upstream/
│   │   └── atlassian-client.ts  # Atlassian MCP 호출 클라이언트
│   └── types.ts              # 공유 타입 정의
├── patterns.json             # 민감정보 패턴 정의
└── tests/
    ├── filter.test.ts        # 필터 엔진 단위 테스트
    ├── entropy.test.ts       # 엔트로피 계산 테스트
    └── redactor.test.ts      # REDACT 처리 테스트
```

### 4.2 Upstream 통신 방식

Gateway가 Atlassian MCP와 통신하는 방식에 두 가지 선택지가 있다:

**Option A: MCP Client로 Atlassian MCP 서버에 연결**
```
Gateway MCP Server → (MCP protocol) → Atlassian MCP Server → Jira API
```
- 장점: MCP 프로토콜 계층을 유지
- 단점: MCP-over-MCP 체이닝의 복잡성

**Option B: 직접 Jira REST API 호출**
```
Gateway MCP Server → (HTTP) → Jira REST API
```
- 장점: 중간 단계 제거, 더 단순
- 단점: Atlassian MCP의 인증/세션 관리를 직접 구현해야 함

**선택: Option B (직접 Jira REST API)**

이유:
- Proxy의 목적이 "필터링"이므로 upstream이 MCP일 필요 없음
- Jira REST API는 잘 문서화되어 있고 안정적
- MCP-over-MCP 체이닝은 디버깅이 어려움
- 인증은 API token 기반으로 단순 (환경변수: JIRA_BASE_URL, JIRA_API_TOKEN, JIRA_USER_EMAIL)

### 4.3 인증 설정

```typescript
// 환경변수 기반
interface JiraConfig {
  baseUrl: string;       // JIRA_BASE_URL: https://your-domain.atlassian.net
  apiToken: string;      // JIRA_API_TOKEN: Jira API token
  userEmail: string;     // JIRA_USER_EMAIL: 인증 이메일
}

// Basic Auth: email:token → base64
// Header: Authorization: Basic <base64>
```

환경변수는 `.env`에 저장하되 `.gitignore`에 추가.
플러그인 설치 시 초기 설정 가이드 제공.

---

## 5. patterns.json 공유 전략

Sensitive Filter는 Jira Gateway MCP와 CKS MCP(Phase 3-4) 모두에서 사용한다.

```
coding-agent/
├── shared/
│   └── patterns.json      ← SSoT (Single Source of Truth)
└── tools/
    ├── jira-gateway-mcp/
    │   └── (환경변수 PATTERNS_PATH로 shared/patterns.json 참조)
    └── cks-mcp/
        └── (환경변수 CKS_PATTERNS_PATH로 shared/patterns.json 참조)
```

### 5.1 패턴 커스터마이징

유저가 프로젝트별 패턴을 추가할 수 있도록 override 메커니즘 제공:

```
로드 순서:
1. shared/patterns.json (기본 패턴)
2. .coding-agent/custom-patterns.json (프로젝트별 추가 패턴, 있으면)

merge 규칙: 동일 id → custom이 override. 새 id → 추가.
```

---

## 6. 에러 처리

| 시나리오 | 처리 |
|----------|------|
| Jira API 인증 실패 | "Jira 인증 실패. JIRA_API_TOKEN을 확인하세요." + 파이프라인 중단 |
| Jira API rate limit | 지수 백오프 재시도 (최대 3회) 후 실패 보고 |
| 티켓 미존재 | "STABLE-9999 티켓을 찾을 수 없습니다." + 파이프라인 중단 |
| 네트워크 오류 | 재시도 (최대 3회) 후 실패 보고 |
| patterns.json 파싱 실패 | 기본 패턴(하드코딩 최소셋)으로 폴백 + 경고 |
| 필터 실행 중 오류 | fail-safe: 필터 실패 시 차단 (통과시키지 않음) |

fail-safe 원칙: **필터가 실패하면 데이터를 통과시키지 않는다.** 필터 오류 자체가 보안 위험이 될 수 있으므로, 오류 시에는 차단 후 유저에게 보고.

---

## 7. Phase 2 완료 기준

- [ ] Jira Gateway MCP 서버가 MCP 프로토콜로 동작
- [ ] 읽기 tool (read_ticket, read_comments, search)에 Sensitive Filter 적용
- [ ] 쓰기 tool (add_comment, update_status)은 passthrough
- [ ] patterns.json의 모든 패턴이 정상 매칭
- [ ] Shannon entropy 기반 고랜덤 문자열 탐지 동작
- [ ] REDACT/BLOCK/WARN 3단계 처리 동작
- [ ] Jira REST API 인증 + 호출 동작
- [ ] 필터 엔진 단위 테스트 통과
- [ ] fail-safe: 필터 오류 시 차단 동작 확인
