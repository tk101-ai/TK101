# TK101 플랫폼 뼈대 구축 Design Document

> **Summary**: Clean Architecture 기반 FastAPI + Next.js 플랫폼 뼈대. 4-layer 분리로 장기 유지보수성 확보
>
> **Project**: TK101 사내 AI 자동화 플랫폼
> **Version**: 0.1.0
> **Author**: TK101 (junki7853)
> **Date**: 2026-04-16
> **Status**: Draft
> **Planning Doc**: [tk101-platform-foundation.plan.md](../../01-plan/features/tk101-platform-foundation.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | [Schema Definition](../../01-plan/schema.md) | ⏳ Pending (next) |
| Phase 2 | [Coding Conventions](../../01-plan/conventions.md) | ⏳ Pending (next) |
| Phase 3 | Mockup | N/A (백오피스 단순 UI는 Sprint 1에서 바로 구현) |
| Phase 4 | API Spec | ✅ (이 문서 §4) |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | AI API 보유 → 직원용 플랫폼 없음. 회계 자동화(이사님 요청)의 기반 인프라 필요 |
| **WHO** | 관리자(TK101), 직원 40명, 이사님 (회계 결과 확인자) |
| **RISK** | 1인 개발자 병목. Clean Architecture 초기 세팅에 3~5일 소요 예상. 회계 완성 목표 5월 중순. |
| **SUCCESS** | 로그인+대시보드+AI대화+CI/CD 자동배포 + **4 레이어 분리 유지** + 테스트 커버리지 80% |
| **SCOPE** | 1단계 뼈대만. 회계/카카오톡/멀티AI/NAS는 2~3단계 별도 PDCA. 4/21 미팅은 "설계+로그인 데모" 수준 |

---

## 1. Overview

### 1.1 Design Goals

1. **장기 유지보수성 최우선**: 40명 규모 × 5개 팀 모듈을 3년 이상 운영할 수 있는 견고한 설계
2. **회계 로직 정확도 보장**: Domain 레이어 순수 함수로 은행 파싱/매칭 로직 단위 테스트 가능 (DB 의존 없음)
3. **멀티 AI 대응 준비**: Infrastructure 레이어 Adapter 패턴으로 Claude→OpenAI→Gemini 교체 용이
4. **1인 유지보수 + Claude Code 친화**: 명확한 레이어 경계로 AI가 빠르게 탐색 가능한 예측 가능한 구조
5. **테스트 커버리지 80%+**: 레이어 분리로 단위 테스트 작성 용이

### 1.2 Design Principles

- **Dependency Inversion**: 상위 레이어가 하위 레이어의 인터페이스에 의존
- **Single Responsibility**: 레이어별/모듈별 단일 책임
- **Pure Domain**: Domain 레이어는 외부 의존성 0 (FastAPI/SQLAlchemy 의존 안 함)
- **Explicit over Implicit**: 매직 없이 명시적 구성 (FastAPI Depends, 명시적 DI)
- **Test First**: Domain 로직은 TDD로 작성 (ECC `tdd-guide` 활용)

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 기준 | Option A: Minimal | Option B: **Clean Architecture** | Option C: Pragmatic |
|------|:-:|:-:|:-:|
| **Approach** | 평면 폴더 구조 | 4-layer 엄격 분리 | Feature-based 모듈 |
| **New Files** | ~25 | ~60 | ~40 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (3년 시점 부담) | **High (3년 이후에도 견고)** | High |
| **Effort (Sprint 1)** | Low | **High (Sprint 0 필요)** | Medium |
| **Risk** | 리팩토링 부채 누적 | 초기 세팅 오버헤드 | 레이어 경계 모호 |
| **회계 모듈 정확도** | 낮음 (DB 의존 테스트) | **높음 (Domain 순수 테스트)** | 중간 |
| **멀티 AI 전환 용이성** | 낮음 | **높음 (Adapter)** | 중간 |
| **Recommendation** | 핫픽스/프로토타입 | **장기 서비스 (선택됨)** | 균형적 MVP |

**Selected**: Option B — Clean Architecture

**Rationale**:
- 회계 자동화 완성 목표가 5월 중순 → Sprint 0(3일)의 아키텍처 세팅 시간 확보 가능
- 3년 이상 운영, 5개 팀 모듈 확장 예정 → 장기 관점에서 B의 투자 대비 수익 명확
- 회계 로직은 돈을 다루므로 Domain 레이어 단위 테스트로 정확도 담보 필요
- 멀티 AI(OpenAI, Gemini) 전환이 3단계 계획에 있음 → Adapter 패턴이 필수
- Claude Code 기반 유지보수 가정 → Clean Architecture의 예측 가능한 구조가 오히려 AI에 유리

### 2.1 Component Diagram

```
┌───────────────────────────────────────────────────────────────┐
│                     Tencent CVM (Docker Compose)                │
│                                                                 │
│  ┌───────────────┐    ┌──────────────────┐    ┌─────────────┐ │
│  │   Next.js     │    │    FastAPI       │    │ PostgreSQL  │ │
│  │  (Frontend)   │◄──►│   (Backend)      │◄──►│   + pgvector│ │
│  │  Port 3000    │    │   Port 8000      │    │  Port 5432  │ │
│  └───────────────┘    └────────┬─────────┘    └─────────────┘ │
│                                │                                │
│                                ▼                                │
│                       ┌─────────────────┐                      │
│                       │     Redis       │                      │
│                       │  (Session+Cache)│                      │
│                       │   Port 6379     │                      │
│                       └─────────────────┘                      │
│                                                                 │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
                     ┌────────────────────────┐
                     │  Anthropic Claude API  │
                     │  (외부 AI 서비스)        │
                     └────────────────────────┘

      GitHub Repo  ─────►  GitHub Actions  ─────►  CVM 배포
```

### 2.2 Clean Architecture Layers (Backend)

```
┌───────────────────────────────────────────────────────────────┐
│  Presentation Layer (app/api/)                                 │
│   - FastAPI routers, Pydantic schemas (req/res), middleware     │
│   - HTTP 관심사만 처리. 비즈니스 로직 없음                        │
├───────────────────────────────────────────────────────────────┤
│  Application Layer (app/use_cases/)                            │
│   - Use Case 클래스 (AuthenticateUser, CreateDepartment 등)     │
│   - Domain + Infrastructure를 조합하여 비즈니스 흐름 실행         │
├───────────────────────────────────────────────────────────────┤
│  Domain Layer (app/domain/)                                    │
│   - Entity (User, Department, ChatMessage), Value Object        │
│   - Repository 인터페이스 (ABC)                                  │
│   - Domain Service (비즈니스 규칙)                               │
│   - 외부 의존성 0. 순수 Python.                                  │
├───────────────────────────────────────────────────────────────┤
│  Infrastructure Layer (app/infrastructure/)                    │
│   - SQLAlchemy Repository 구현체                                 │
│   - Claude API Adapter (LLMProvider 인터페이스 구현)             │
│   - Redis 클라이언트, JWT 핸들러, 비밀번호 해셔                   │
│   - Domain 인터페이스를 구현 (Dependency Inversion)              │
└───────────────────────────────────────────────────────────────┘

의존 방향: Presentation → Application → Domain ← Infrastructure
                                          (Infrastructure가 Domain에 의존)
```

### 2.3 Data Flow (예시: 로그인)

```
1. POST /api/v1/auth/login (email, password)
     │
     ▼
2. [Presentation] LoginRequest (Pydantic) 검증
     │
     ▼
3. [Presentation] AuthenticateUserUseCase (DI로 주입)
     │
     ▼
4. [Application] UseCase 실행:
     a. UserRepository.find_by_email() 호출  ───► [Infrastructure: SQLAlchemy]
     b. PasswordHasher.verify() 호출         ───► [Infrastructure: bcrypt]
     c. 검증 실패 시 DomainException 발생    ───► [Domain]
     d. JWTProvider.issue() 호출             ───► [Infrastructure: PyJWT]
     │
     ▼
5. [Presentation] LoginResponse 직렬화 → HTTP 200
```

---

## 3. Data Model

### 3.1 Entity Definition (Domain Layer - Pure Python)

```python
# app/domain/entities/user.py
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"

@dataclass(frozen=True)  # 불변 Entity
class User:
    id: Optional[int]
    email: str
    password_hash: str
    name: str
    role: UserRole
    department_id: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    def can_access_department(self, dept_id: int) -> bool:
        """Domain 규칙: 관리자는 모든 부서, 그 외는 자기 부서만"""
        if self.role == UserRole.ADMIN:
            return True
        return self.department_id == dept_id


# app/domain/entities/department.py
@dataclass(frozen=True)
class Department:
    id: Optional[int]
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


# app/domain/entities/chat_message.py
@dataclass(frozen=True)
class ChatMessage:
    id: Optional[int]
    user_id: int
    model: str  # "haiku" | "sonnet" | "opus"
    input_tokens: int
    output_tokens: int
    messages: list[dict]  # [{"role": "user", "content": "..."}, ...]
    created_at: datetime
```

### 3.2 Repository Interfaces (Domain Layer)

```python
# app/domain/repositories/user_repository.py
from abc import ABC, abstractmethod
from typing import Optional
from app.domain.entities.user import User

class UserRepository(ABC):
    @abstractmethod
    async def find_by_id(self, user_id: int) -> Optional[User]: ...

    @abstractmethod
    async def find_by_email(self, email: str) -> Optional[User]: ...

    @abstractmethod
    async def save(self, user: User) -> User: ...

    @abstractmethod
    async def list_by_department(self, dept_id: int) -> list[User]: ...

    @abstractmethod
    async def delete(self, user_id: int) -> None: ...
```

### 3.3 Entity Relationships

```
[Department] 1 ────── N [User] 1 ────── N [ChatMessage]
                         │
                         └── role: admin/manager/staff

[Department] 1 ────── N [ApiUsageMonthly]  (집계 테이블)
```

### 3.4 Database Schema (PostgreSQL)

```sql
-- 부서
CREATE TABLE departments (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 사용자
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    name            VARCHAR(100) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'staff'
                    CHECK (role IN ('admin', 'manager', 'staff')),
    department_id   INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_department ON users(department_id);

-- AI 대화 이력
CREATE TABLE chat_messages (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model           VARCHAR(50) NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    messages        JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_chat_user_created ON chat_messages(user_id, created_at DESC);

-- API 사용량 월별 집계
CREATE TABLE api_usage_monthly (
    id                  SERIAL PRIMARY KEY,
    department_id       INTEGER REFERENCES departments(id) ON DELETE CASCADE,
    year_month          VARCHAR(7) NOT NULL,
    total_requests      INTEGER NOT NULL DEFAULT 0,
    total_input_tokens  BIGINT NOT NULL DEFAULT 0,
    total_output_tokens BIGINT NOT NULL DEFAULT 0,
    estimated_cost_usd  NUMERIC(10,4) NOT NULL DEFAULT 0,
    UNIQUE(department_id, year_month)
);

-- Refresh Token 저장 (Redis에도 caching)
CREATE TABLE refresh_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(255) NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
```

---

## 4. API Specification

### 4.1 Endpoint List (Sprint 1 범위)

| Method | Path | Description | Auth | Role |
|--------|------|-------------|------|------|
| POST | /api/v1/auth/login | 로그인 | No | - |
| POST | /api/v1/auth/refresh | 토큰 갱신 | Refresh Token | - |
| POST | /api/v1/auth/logout | 로그아웃 | Yes | all |
| GET | /api/v1/auth/me | 내 정보 조회 | Yes | all |
| GET | /api/v1/departments | 부서 목록 | Yes | all |
| POST | /api/v1/departments | 부서 생성 | Yes | admin |
| PATCH | /api/v1/departments/:id | 부서 수정 | Yes | admin |
| DELETE | /api/v1/departments/:id | 부서 삭제 | Yes | admin |
| GET | /api/v1/users | 사용자 목록 | Yes | admin, manager |
| POST | /api/v1/users | 사용자 생성 | Yes | admin |
| GET | /api/v1/users/:id | 사용자 상세 | Yes | admin, self |
| PATCH | /api/v1/users/:id | 사용자 수정 | Yes | admin, self(부분) |
| DELETE | /api/v1/users/:id | 사용자 삭제 | Yes | admin |
| POST | /api/v1/chat | Claude API 대화 | Yes | all |
| GET | /api/v1/chat/history | 내 대화 이력 | Yes | all |
| GET | /health | 헬스체크 | No | - |

### 4.2 공통 응답 포맷

```json
// 성공
{
  "data": { ... },
  "pagination": {            // 목록 응답 시
    "total": 100,
    "page": 1,
    "limit": 20
  }
}

// 에러
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Email is required",
    "details": {
      "fieldErrors": {
        "email": "Required field"
      }
    }
  }
}
```

### 4.3 Detailed Specification

#### `POST /api/v1/auth/login`

**Request:**
```json
{
  "email": "user@tk101.com",
  "password": "SecurePassword123"
}
```

**Response (200 OK):**
```json
{
  "data": {
    "access_token": "eyJhbGc...",
    "refresh_token": "rt_abc123...",
    "token_type": "Bearer",
    "expires_in": 1800,
    "user": {
      "id": 1,
      "email": "user@tk101.com",
      "name": "홍길동",
      "role": "staff",
      "department": { "id": 1, "name": "마케팅1팀" }
    }
  }
}
```

**Errors:**
- `400 VALIDATION_ERROR`: 이메일/비밀번호 누락
- `401 INVALID_CREDENTIALS`: 이메일/비밀번호 불일치
- `403 USER_INACTIVE`: 비활성 계정
- `429 TOO_MANY_ATTEMPTS`: Rate limit (IP당 분당 10회)

#### `POST /api/v1/chat`

**Request:**
```json
{
  "model": "haiku",
  "messages": [
    {"role": "user", "content": "이 이메일을 요약해줘"}
  ],
  "max_tokens": 2048
}
```

**Response (200 OK):**
```json
{
  "data": {
    "id": 123,
    "model": "haiku",
    "message": {
      "role": "assistant",
      "content": "요약: ..."
    },
    "usage": {
      "input_tokens": 150,
      "output_tokens": 80,
      "estimated_cost_usd": 0.0012
    }
  }
}
```

---

## 5. UI/UX Design

### 5.1 Screen Layout (Sprint 1 범위)

**로그인 페이지** `/login`
```
┌───────────────────────────────────┐
│                                   │
│         TK101 AI Platform          │
│                                   │
│     ┌───────────────────────┐     │
│     │ Email                 │     │
│     └───────────────────────┘     │
│     ┌───────────────────────┐     │
│     │ Password              │     │
│     └───────────────────────┘     │
│     [    로그인 버튼      ]        │
│                                   │
└───────────────────────────────────┘
```

**대시보드** `/dashboard` (로그인 후 랜딩)
```
┌───────────────────────────────────────────────┐
│ [TK101] 홍길동(마케팅1팀)   [로그아웃] [설정] │
├───────────────────────────────────────────────┤
│ 사이드바             │ 메인 영역               │
│ - 대시보드            │ ┌─────────────────────┐ │
│ - AI 채팅            │ │ Claude와 대화하기    │ │
│ - 내 이력            │ │                     │ │
│ (admin)              │ │ [메시지 입력...]     │ │
│ - 사용자 관리         │ │  [Haiku/Sonnet]     │ │
│ - 부서 관리          │ └─────────────────────┘ │
└───────────────────────────────────────────────┘
```

**백오피스: 사용자 관리** `/admin/users`
```
┌──────────────────────────────────────────────────┐
│ 사용자 관리                     [+ 사용자 추가]   │
├──────────────────────────────────────────────────┤
│ 이름    │ 이메일          │ 부서    │ 역할  │ 작업│
│ 홍길동  │ hong@tk101.com  │ 마케팅1 │ staff │ 수정│
│ 김철수  │ kim@tk101.com   │ 회계    │ manager│ 수정│
└──────────────────────────────────────────────────┘
```

### 5.2 User Flow

```
[로그인 페이지] ─► 로그인 성공 ─► [대시보드]
                                      ├─► [AI 채팅] ─► Claude 대화
                                      ├─► [내 이력] ─► 지난 대화 목록
                                      └─► (admin) [관리] ─► 사용자/부서 CRUD
```

### 5.3 Component List (Frontend - Feature-based + Clean)

| Component | Layer | Location | Responsibility |
|-----------|-------|----------|----------------|
| `LoginForm` | Presentation | `src/features/auth/components/` | 로그인 폼 UI |
| `useAuth` | Application | `src/features/auth/hooks/` | 인증 상태 관리 훅 |
| `authService` | Application | `src/features/auth/services/` | 로그인/로그아웃 비즈니스 흐름 |
| `authApi` | Infrastructure | `src/features/auth/api/` | 백엔드 API 호출 |
| `User`, `AuthResult` | Domain | `src/features/auth/types/` | 타입 정의 |
| `ChatInterface` | Presentation | `src/features/chat/components/` | AI 채팅 UI |
| `useChat` | Application | `src/features/chat/hooks/` | 대화 상태 훅 |
| `chatApi` | Infrastructure | `src/features/chat/api/` | /api/v1/chat 호출 |
| `UserList`, `UserForm` | Presentation | `src/features/admin/components/` | 사용자 관리 UI |
| `Button`, `Input`, `Card` | Shared UI | `src/components/ui/` | shadcn/ui 기반 공용 |
| `apiClient` | Infrastructure | `src/lib/api-client.ts` | fetch 래퍼 + 토큰 관리 |

### 5.4 Page UI Checklist

#### 로그인 페이지 (`/login`)

- [ ] Input: Email 필드 (required, email format validation)
- [ ] Input: Password 필드 (required, type="password", 최소 8자)
- [ ] Button: 로그인 (submit, disabled when form invalid)
- [ ] Message: 에러 toast (401 INVALID_CREDENTIALS 시 "이메일 또는 비밀번호가 올바르지 않습니다")
- [ ] Loading: 제출 시 버튼 로딩 스피너
- [ ] Redirect: 성공 시 `/dashboard`로 이동

#### 대시보드 (`/dashboard`)

- [ ] Header: 사용자명 + 부서명 표시 (예: "홍길동(마케팅1팀)")
- [ ] Header: 로그아웃 버튼
- [ ] Sidebar: 대시보드/AI 채팅/내 이력 메뉴 (항상 표시)
- [ ] Sidebar: admin 역할일 때만 "사용자 관리"/"부서 관리" 메뉴 표시
- [ ] Main: AI 채팅 인터페이스 (`ChatInterface` 컴포넌트)
- [ ] Chat: 모델 선택 드롭다운 (Haiku 기본, Sonnet, Opus 3개)
- [ ] Chat: 메시지 입력 textarea (Enter 전송, Shift+Enter 줄바꿈)
- [ ] Chat: 대화 내역 스크롤 영역 (사용자/AI 메시지 구분 표시)
- [ ] Chat: 토큰 사용량 표시 (예: "150→80 토큰, $0.0012")

#### 사용자 관리 (`/admin/users`, admin 전용)

- [ ] Button: "사용자 추가" (우측 상단)
- [ ] Table: 이름 / 이메일 / 부서 / 역할 / 작업 컬럼
- [ ] Table: 페이지네이션 (20개씩)
- [ ] Table: 검색 (이름 또는 이메일)
- [ ] Filter: 부서 드롭다운 (5개 부서 + "전체")
- [ ] Filter: 역할 드롭다운 (admin/manager/staff + "전체")
- [ ] Action: "수정" 버튼 → 모달로 수정 폼
- [ ] Action: "삭제" 버튼 → 확인 다이얼로그
- [ ] Modal: 사용자 추가/수정 (이메일, 이름, 비밀번호, 부서, 역할 필드)
- [ ] Guard: admin 외 접근 시 403 페이지로 redirect

#### 부서 관리 (`/admin/departments`, admin 전용)

- [ ] Button: "부서 추가"
- [ ] List: 부서명 + 설명 + 소속 인원 수 표시
- [ ] Action: 수정/삭제
- [ ] Validation: 부서 삭제 시 소속 사용자 있으면 경고 (사용자 department_id → NULL)

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | HTTP | Message | Cause | Handling |
|------|:----:|---------|-------|----------|
| VALIDATION_ERROR | 400 | 입력값이 올바르지 않습니다 | Pydantic 검증 실패 | fieldErrors 반환, 클라이언트 폼 표시 |
| UNAUTHORIZED | 401 | 인증이 필요합니다 | JWT 누락/만료 | 로그인 페이지로 redirect |
| INVALID_CREDENTIALS | 401 | 이메일 또는 비밀번호가 올바르지 않습니다 | 로그인 실패 | 폼에 에러 표시 |
| FORBIDDEN | 403 | 권한이 없습니다 | RBAC 검증 실패 | 403 페이지 표시 |
| NOT_FOUND | 404 | 리소스를 찾을 수 없습니다 | 리소스 미존재 | 404 페이지 |
| CONFLICT | 409 | 이미 존재하는 데이터입니다 | 이메일 중복 등 | 폼에 에러 표시 |
| TOO_MANY_REQUESTS | 429 | 너무 많은 요청입니다 | Rate limit | 재시도 시간 표시 |
| INTERNAL_ERROR | 500 | 서버 오류가 발생했습니다 | 서버 예외 | 로그 기록 + 범용 에러 UI |
| EXTERNAL_API_ERROR | 502 | 외부 서비스 오류 | Claude API 실패 | 재시도 안내 |

### 6.2 Error Response Format (공통)

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "이메일 형식이 올바르지 않습니다",
    "details": {
      "fieldErrors": {
        "email": "Invalid email format"
      }
    }
  }
}
```

### 6.3 Exception Hierarchy (Domain Layer)

```python
# app/domain/exceptions.py
class DomainException(Exception):
    """비즈니스 규칙 위반 (400대 에러에 매핑)"""
    code: str = "DOMAIN_ERROR"
    http_status: int = 400

class InvalidCredentialsError(DomainException):
    code = "INVALID_CREDENTIALS"
    http_status = 401

class ForbiddenError(DomainException):
    code = "FORBIDDEN"
    http_status = 403

class NotFoundError(DomainException):
    code = "NOT_FOUND"
    http_status = 404

class DuplicateError(DomainException):
    code = "CONFLICT"
    http_status = 409
```

Presentation Layer에서 `DomainException` → HTTP 응답 매핑 미들웨어 구현.

---

## 7. Security Considerations

- [x] **Input validation**: Pydantic 스키마로 모든 입력 검증 (Presentation 레이어)
- [x] **SQL Injection 방지**: SQLAlchemy ORM만 사용, raw SQL 금지
- [x] **XSS 방지**: Next.js 기본 이스케이프, `dangerouslySetInnerHTML` 금지
- [x] **비밀번호**: bcrypt 해싱 (cost factor 12), 평문 저장 금지
- [x] **JWT**: Access Token 30분, Refresh Token 14일, HS256 서명
- [x] **CSRF**: JWT 사용으로 세션 쿠키 기반 CSRF 위험 최소화. SameSite=Lax 설정
- [x] **HTTPS**: Nginx reverse proxy + Let's Encrypt (Sprint 2 Task)
- [x] **Rate Limiting**: slowapi 미들웨어. 로그인 IP당 분당 10회, 전체 API 사용자당 분당 60회
- [x] **CORS**: 프론트 도메인만 허용 (환경변수 `ALLOWED_ORIGINS`)
- [x] **RBAC**: Domain 엔티티의 `can_access_department()` 메서드로 권한 규칙
- [x] **Secrets 관리**: .env(로컬) + GitHub Secrets(CI/CD), 커밋 금지
- [x] **로그 보안**: 비밀번호/토큰은 로그 마스킹
- [ ] **Audit log** (Sprint 2): 관리자 액션 (사용자 CRUD, 권한 변경) 감사 로그

**Security Review**: Sprint 1 완료 시 ECC `security-reviewer` 에이전트로 검증.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0: Domain Unit Tests | Entity, Domain Service 순수 로직 | pytest | Do |
| L1: API Tests | FastAPI 엔드포인트 | pytest + httpx AsyncClient | Do |
| L2: UI Action Tests | Next.js 페이지 동작 | Playwright | Do |
| L3: E2E Scenario Tests | 로그인→대시보드→채팅 전체 흐름 | Playwright | Do |

### 8.2 L0: Domain Unit Test Scenarios (Clean Architecture 장점)

| # | Target | Test Description | Expected |
|---|--------|-----------------|----------|
| 1 | `User.can_access_department()` | admin은 모든 부서 접근 가능 | `True` 반환 |
| 2 | `User.can_access_department()` | staff는 자기 부서만 | 본인 부서 `True`, 타부서 `False` |
| 3 | `PasswordHasher` (인터페이스) | 해싱 후 검증 일치 | `verify(hash, plain) == True` |
| 4 | `JWTProvider` | 발급된 토큰 검증 통과 | payload의 user_id 복원 |
| 5 | `AuthenticateUserUseCase` | 잘못된 비밀번호 시 예외 | `InvalidCredentialsError` |
| 6 | `AuthenticateUserUseCase` | 비활성 사용자 로그인 시 | `ForbiddenError` |

### 8.3 L1: API Test Scenarios

| # | Endpoint | Method | Test Description | Status | Response |
|---|----------|--------|-----------------|:------:|----------|
| 1 | /api/v1/auth/login | POST | 올바른 자격증명 | 200 | `.data.access_token` 존재 |
| 2 | /api/v1/auth/login | POST | 잘못된 비밀번호 | 401 | `.error.code` = "INVALID_CREDENTIALS" |
| 3 | /api/v1/auth/login | POST | 이메일 누락 | 400 | `.error.details.fieldErrors.email` 존재 |
| 4 | /api/v1/auth/me | GET | 토큰 없이 요청 | 401 | `.error.code` = "UNAUTHORIZED" |
| 5 | /api/v1/auth/me | GET | 유효 토큰 | 200 | `.data.email` 존재 |
| 6 | /api/v1/users | GET | staff 권한으로 요청 | 403 | `.error.code` = "FORBIDDEN" |
| 7 | /api/v1/users | GET | admin 권한으로 요청 | 200 | `.data`는 배열 |
| 8 | /api/v1/users | POST | 중복 이메일 | 409 | `.error.code` = "CONFLICT" |
| 9 | /api/v1/chat | POST | 유효 요청 | 200 | `.data.message.content` 존재 |
| 10 | /api/v1/chat | POST | 1분에 61회 요청 | 429 | `.error.code` = "TOO_MANY_REQUESTS" |
| 11 | /health | GET | 서버 확인 | 200 | `{"status": "ok"}` |

### 8.4 L2: UI Action Test Scenarios

| # | Page | Action | Expected Result |
|---|------|--------|----------------|
| 1 | /login | 빈 폼 제출 | 로그인 버튼 비활성화 |
| 2 | /login | 잘못된 이메일 형식 입력 | 필드 에러 메시지 표시 |
| 3 | /login | 잘못된 자격증명 제출 | Toast 에러 표시 |
| 4 | /login | 올바른 자격증명 제출 | `/dashboard`로 redirect |
| 5 | /dashboard | 채팅 입력 후 전송 | 메시지 + AI 응답 순차 표시 |
| 6 | /dashboard | 로그아웃 클릭 | `/login`으로 redirect |
| 7 | /admin/users | staff 권한으로 접근 | 403 페이지로 redirect |
| 8 | /admin/users | admin으로 사용자 추가 | 목록에 신규 사용자 표시 |

### 8.5 L3: E2E Scenario Tests

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 전체 인증 흐름 | 로그인→대시보드→내 정보 확인→로그아웃 | 각 단계 정상 진행 |
| 2 | AI 채팅 흐름 | 로그인→채팅→메시지 전송→응답 확인→이력 조회 | DB에 메시지 저장 확인 |
| 3 | 관리자 사용자 관리 | admin 로그인→사용자 생성→신규 사용자 로그인→성공 | 신규 사용자 정상 로그인 |
| 4 | 권한 분리 | staff 로그인→/admin/users 접근 시도 | 403 페이지 표시 |
| 5 | 토큰 갱신 | 로그인→30분 대기(mock)→자동 refresh→요청 성공 | 중단 없이 계속 사용 가능 |

### 8.6 Seed Data Requirements

| Entity | 최소 개수 | 필수 필드 |
|--------|:------:|----------|
| Department | 5 | 마케팅1팀, 마케팅2팀, 디자인팀, 신사업팀, 회계팀 |
| User | 3 | admin 1명, manager 1명, staff 1명 (각기 다른 부서) |
| 테스트 사용자 비밀번호 | - | `TestPass123!` (통일) |

**시드 스크립트**: `backend/scripts/seed.py` (Do phase 첫 작업)

---

## 9. Clean Architecture

### 9.1 Layer Structure (Backend)

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Presentation** | FastAPI routers, Pydantic schemas, middleware | `backend/app/api/v1/` |
| **Application** | Use Cases (비즈니스 흐름 오케스트레이션) | `backend/app/use_cases/` |
| **Domain** | Entity, Value Object, Repository 인터페이스, Domain Service | `backend/app/domain/` |
| **Infrastructure** | SQLAlchemy Repo 구현체, Claude Adapter, JWT, Redis | `backend/app/infrastructure/` |

### 9.2 Dependency Rules

```
Presentation ──► Application ──► Domain ◄── Infrastructure
                       │                          ▲
                       └──────────────────────────┘
                         (Application이 Infrastructure의 구현체 사용,
                          단 Domain 인터페이스를 통해서만)

규칙:
- Domain은 외부 의존성 0 (FastAPI, SQLAlchemy import 금지)
- Infrastructure는 Domain 인터페이스 구현 (Dependency Inversion)
- Presentation은 Application을 통해서만 Domain 접근
- Application은 Infrastructure 구현체를 직접 import하지 않음
  (FastAPI Depends로 주입받음)
```

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| Presentation | Application, Domain | Infrastructure 직접 import 금지 (DI 사용) |
| Application | Domain 만 | Presentation, Infrastructure (구현체) |
| Domain | 외부 의존성 없음 | 모든 외부 레이어 |
| Infrastructure | Domain 만 | Application, Presentation |

### 9.4 Feature Module Structure (Backend)

```
backend/app/
├── main.py                          # FastAPI 앱 진입점
├── config.py                        # 환경변수 (Pydantic Settings)
├── container.py                     # DI 컨테이너 (의존성 wiring)
│
├── api/v1/                          # [Presentation]
│   ├── __init__.py
│   ├── deps.py                      # FastAPI Depends (인증, 현재 사용자)
│   ├── middleware/
│   │   ├── error_handler.py         # DomainException → HTTP 매핑
│   │   ├── rate_limit.py            # slowapi
│   │   └── request_logging.py
│   ├── routers/
│   │   ├── auth.py                  # 로그인/로그아웃/refresh
│   │   ├── users.py                 # 사용자 CRUD
│   │   ├── departments.py           # 부서 CRUD
│   │   ├── chat.py                  # Claude API 프록시
│   │   └── health.py                # 헬스체크
│   └── schemas/                     # Pydantic 요청/응답
│       ├── auth.py
│       ├── user.py
│       ├── department.py
│       └── chat.py
│
├── use_cases/                       # [Application]
│   ├── auth/
│   │   ├── authenticate_user.py
│   │   ├── refresh_token.py
│   │   └── logout.py
│   ├── user/
│   │   ├── create_user.py
│   │   ├── list_users.py
│   │   ├── update_user.py
│   │   └── delete_user.py
│   ├── department/
│   │   └── ... (CRUD 각각)
│   └── chat/
│       └── send_message.py          # LLMProvider 인터페이스 사용
│
├── domain/                          # [Domain] - 외부 의존성 0
│   ├── entities/
│   │   ├── user.py
│   │   ├── department.py
│   │   └── chat_message.py
│   ├── value_objects/
│   │   ├── email.py                 # 검증 로직 포함된 VO
│   │   └── password.py
│   ├── repositories/                # 인터페이스(ABC)
│   │   ├── user_repository.py
│   │   ├── department_repository.py
│   │   └── chat_message_repository.py
│   ├── services/                    # Domain Service
│   │   └── password_hasher.py       # 인터페이스
│   ├── providers/                   # 외부 서비스 추상화
│   │   ├── llm_provider.py          # Claude/OpenAI/Gemini 추상
│   │   └── jwt_provider.py          # 인터페이스
│   └── exceptions.py
│
└── infrastructure/                  # [Infrastructure]
    ├── database/
    │   ├── session.py               # SQLAlchemy async session
    │   └── models/                  # SQLAlchemy ORM 모델
    │       ├── user_model.py
    │       ├── department_model.py
    │       └── chat_message_model.py
    ├── repositories/                # Domain 인터페이스 구현체
    │   ├── sqlalchemy_user_repository.py
    │   ├── sqlalchemy_department_repository.py
    │   └── sqlalchemy_chat_message_repository.py
    ├── services/
    │   └── bcrypt_password_hasher.py
    ├── providers/
    │   ├── anthropic_llm_provider.py   # Claude 구현
    │   ├── openai_llm_provider.py      # (3단계 준비만, 미구현)
    │   └── pyjwt_provider.py
    └── redis_client.py
```

### 9.5 Frontend Clean Architecture (Next.js)

```
frontend/src/
├── app/                             # [Presentation] Next.js App Router
│   ├── (auth)/
│   │   └── login/page.tsx
│   ├── (main)/
│   │   ├── layout.tsx               # 사이드바 레이아웃 (인증 가드)
│   │   ├── dashboard/page.tsx
│   │   └── admin/
│   │       ├── users/page.tsx
│   │       └── departments/page.tsx
│   ├── api/                         # Next.js Route Handlers (BFF if needed)
│   └── layout.tsx                   # 루트 레이아웃
│
├── features/                        # Feature 모듈 (레이어 내포)
│   ├── auth/
│   │   ├── components/              # [Presentation]
│   │   │   └── LoginForm.tsx
│   │   ├── hooks/                   # [Application]
│   │   │   └── useAuth.ts
│   │   ├── services/                # [Application]
│   │   │   └── authService.ts
│   │   ├── api/                     # [Infrastructure]
│   │   │   └── authApi.ts
│   │   └── types/                   # [Domain]
│   │       └── index.ts
│   ├── chat/
│   │   └── ... (동일 구조)
│   └── admin/
│       └── ... (동일 구조)
│
├── components/ui/                   # shadcn/ui 공용 컴포넌트
├── lib/
│   ├── api-client.ts                # fetch 래퍼 + 토큰 자동 갱신
│   └── utils.ts
└── types/                           # 글로벌 타입
```

### 9.6 This Feature's Layer Assignment (예시: 로그인)

| Component | Layer | Location |
|-----------|-------|----------|
| `User` Entity | Domain | `backend/app/domain/entities/user.py` |
| `UserRepository` interface | Domain | `backend/app/domain/repositories/user_repository.py` |
| `PasswordHasher` interface | Domain | `backend/app/domain/services/password_hasher.py` |
| `AuthenticateUserUseCase` | Application | `backend/app/use_cases/auth/authenticate_user.py` |
| `SqlAlchemyUserRepository` | Infrastructure | `backend/app/infrastructure/repositories/sqlalchemy_user_repository.py` |
| `BcryptPasswordHasher` | Infrastructure | `backend/app/infrastructure/services/bcrypt_password_hasher.py` |
| `auth.py` router | Presentation | `backend/app/api/v1/routers/auth.py` |
| `LoginRequest/Response` schema | Presentation | `backend/app/api/v1/schemas/auth.py` |

---

## 10. Coding Convention Reference

> 정식 Convention 문서는 Phase 2에서 작성 예정 (`docs/01-plan/conventions.md`)

### 10.1 Naming Conventions

| Target | Rule | Example (Python) | Example (TS) |
|--------|------|------------------|--------------|
| Class | PascalCase | `UserRepository` | `UserProfile` |
| Function/method | snake_case / camelCase | `find_by_email()` | `getUserById()` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` | `API_BASE_URL` |
| File (module) | snake_case / PascalCase | `user_repository.py` | `UserProfile.tsx` |
| Folder | snake_case / kebab-case | `use_cases/` | `user-profile/` |
| Interface (ABC) | PascalCase (no `I` prefix) | `UserRepository` | `UserRepository` |
| Implementation | {Tech}{Interface} | `SqlAlchemyUserRepository` | - |

### 10.2 Import Order (Python)

```python
# 1. Standard library
from datetime import datetime
from typing import Optional

# 2. Third-party
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# 3. Domain (inner layer first)
from app.domain.entities.user import User
from app.domain.repositories.user_repository import UserRepository

# 4. Application
from app.use_cases.auth.authenticate_user import AuthenticateUserUseCase

# 5. Infrastructure (only in DI wiring and Presentation)
from app.infrastructure.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository

# 6. Presentation (only within Presentation)
from app.api.v1.schemas.auth import LoginRequest
```

### 10.3 Environment Variables

| Prefix | Purpose | Scope | Example |
|--------|---------|-------|---------|
| (없음) | 공통 설정 | Server | `ENVIRONMENT=production` |
| `DATABASE_` | DB 관련 | Server | `DATABASE_URL` |
| `REDIS_` | Redis 관련 | Server | `REDIS_URL` |
| `JWT_` | 인증 시크릿 | Server | `JWT_SECRET_KEY`, `JWT_ALGORITHM` |
| `ANTHROPIC_` | Claude API | Server | `ANTHROPIC_API_KEY` |
| `NEXT_PUBLIC_` | 클라이언트 접근 | Browser | `NEXT_PUBLIC_API_URL` |

### 10.4 This Feature's Conventions

| Item | Convention |
|------|-----------|
| 에러 처리 | Domain 레이어에서 `DomainException` 발생 → Presentation 미들웨어가 HTTP 응답으로 매핑 |
| Entity 불변성 | `@dataclass(frozen=True)` 사용 (Python), `readonly` 타입 (TS) |
| Repository 반환 타입 | Domain Entity만 반환 (SQLAlchemy 모델 유출 금지) |
| Use Case 시그니처 | `async def execute(self, ...) -> DomainEntity` |
| DI 방법 | FastAPI `Depends()` + 팩토리 함수 (`app/api/v1/deps.py`) |
| 비동기 | 전부 async/await (FastAPI, SQLAlchemy 2.0 async) |
| 프론트 상태 관리 | Server state: TanStack Query / Client state: Zustand |
| 프론트 스타일 | Tailwind + shadcn/ui 컴포넌트 |

---

## 11. Implementation Guide

### 11.1 File Structure (최상위)

```
TK101 AI/
├── backend/                         # FastAPI (Python)
│   ├── app/                         # Clean Architecture 4 레이어
│   ├── alembic/                     # DB 마이그레이션
│   ├── tests/                       # pytest (레이어별 디렉터리)
│   │   ├── unit/                    # Domain + Application 단위 테스트
│   │   ├── integration/             # Infrastructure + API 통합 테스트
│   │   └── e2e/                     # 전체 흐름
│   ├── scripts/
│   │   └── seed.py                  # 시드 데이터
│   ├── Dockerfile
│   ├── pyproject.toml               # uv 또는 poetry
│   └── requirements.txt
│
├── frontend/                        # Next.js (TypeScript)
│   ├── src/
│   ├── tests/
│   │   └── e2e/                     # Playwright
│   ├── Dockerfile
│   ├── package.json
│   └── tsconfig.json
│
├── docker-compose.yml               # 로컬 개발
├── docker-compose.prod.yml          # CVM 배포
├── .env.example
├── .github/
│   └── workflows/
│       └── deploy.yml               # CI/CD
└── docs/                            # PDCA 문서
```

### 11.2 Implementation Order

**Sprint 0 (아키텍처 골조, 3일 예상)**
1. [ ] 프로젝트 디렉터리 구조 생성
2. [ ] `backend/`: Python 환경(uv/poetry), FastAPI, SQLAlchemy, Alembic 세팅
3. [ ] `backend/app/domain/`: Entity + Repository 인터페이스 스켈레톤
4. [ ] `backend/app/infrastructure/database/`: SQLAlchemy 모델 + Alembic 초기 마이그레이션
5. [ ] `backend/app/api/v1/`: FastAPI 앱 + health 엔드포인트
6. [ ] `backend/app/container.py`: DI 컨테이너 wiring
7. [ ] `frontend/`: Next.js + Tailwind + shadcn/ui 초기화
8. [ ] `frontend/src/features/`: feature 모듈 스켈레톤
9. [ ] `docker-compose.yml`: postgres + redis + backend + frontend
10. [ ] `.github/workflows/deploy.yml`: CI/CD 기본 구조

**Sprint 1 (인증 + 기본 UI, 1주)**
11. [ ] Domain Unit Tests: `User`, `PasswordHasher`, `JWTProvider` (TDD)
12. [ ] Infrastructure: `SqlAlchemyUserRepository`, `BcryptPasswordHasher`, `PyjwtProvider`
13. [ ] Application: `AuthenticateUserUseCase`, `RefreshTokenUseCase`
14. [ ] Presentation: `/api/v1/auth/*` 라우터
15. [ ] Seed 스크립트: 5개 부서 + 3명 테스트 사용자
16. [ ] API Tests: 로그인 시나리오 11개
17. [ ] Frontend: 로그인 페이지 + 대시보드 쉘 + 라우팅 가드
18. [ ] E2E Tests: 로그인→대시보드→로그아웃 (Playwright)
19. [ ] CVM 최초 배포 + CI/CD 동작 확인

**Sprint 2 (백오피스 + 채팅, 1주)**
20. [ ] Domain: `Department`, `ChatMessage` Entity + Repository 인터페이스
21. [ ] Infrastructure: 나머지 Repository 구현 + `AnthropicLLMProvider`
22. [ ] Application: 사용자/부서 CRUD Use Case + `SendMessageUseCase`
23. [ ] Presentation: 나머지 라우터 + RBAC Depends
24. [ ] Frontend: 백오피스 UI (사용자/부서 관리)
25. [ ] Frontend: AI 채팅 인터페이스
26. [ ] Rate limiting + 보안 강화 (ECC `security-reviewer` 실행)
27. [ ] 테스트 커버리지 80% 달성 확인
28. [ ] 문서화 (README, API docs)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 프로젝트 골조 | `skeleton` | 디렉터리, FastAPI 앱, Next.js 앱, Docker Compose, Alembic 초기화 | 50-60 |
| Domain + DB | `domain-db` | Domain Entity + Repository 인터페이스 + SQLAlchemy 모델 + 초기 마이그레이션 | 40-50 |
| 인증 (Auth) | `auth` | AuthenticateUserUseCase + auth router + JWT + bcrypt + 로그인 페이지 | 60-80 |
| 대시보드 쉘 | `dashboard-shell` | 로그인 가드 + 사이드바 + 빈 대시보드 페이지 + 로그아웃 | 30-40 |
| CI/CD | `cicd` | GitHub Actions + CVM 배포 스크립트 + 시크릿 설정 | 40-50 |
| 사용자/부서 CRUD | `admin-crud` | Users + Departments Use Cases + Routers + 백오피스 UI | 80-100 |
| AI 채팅 | `chat` | LLMProvider 추상화 + AnthropicLLMProvider + 채팅 UI | 60-80 |
| 테스트 강화 | `test-coverage` | L0/L1/L2/L3 테스트 커버리지 80% 달성 | 50-70 |
| 보안 강화 | `security` | Rate limiting + CORS + HTTPS + security-reviewer | 30-40 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| S1 | Plan + Design | 전체 (현재 완료) | 30-35 |
| S2 (Sprint 0 D1) | Do | `--scope skeleton,domain-db` | 90-110 |
| S3 (Sprint 0 D2~3) | Do | `--scope auth` | 60-80 |
| S4 (Sprint 1) | Do | `--scope dashboard-shell,cicd` | 70-90 |
| S5 (4/21 미팅) | 데모 리허설 | - | 10-20 |
| S6 (Sprint 2 전반) | Do | `--scope admin-crud` | 80-100 |
| S7 (Sprint 2 후반) | Do | `--scope chat` | 60-80 |
| S8 | Do | `--scope test-coverage,security` | 80-110 |
| S9 | Check + Report | 전체 | 40-50 |

**총 예상**: 9 세션, 520~675 turns. 실제 상황에 따라 세션 분할 조정.

### 11.4 4/21 미팅 데모 시나리오 (Sprint 1 중간 성과)

Sprint 1이 4/21까지 완료되지 않을 가능성 높음 (Clean Architecture 세팅 3일 + 인증 3~4일 = 6~7일).

**4/21 미팅에서 보여줄 현실적 성과:**
- ✅ **아키텍처 다이어그램 발표**: Clean Architecture 4 레이어 + 향후 확장성 설명
- ✅ **Docker Compose 실행 시연**: `docker compose up`으로 전체 스택 기동 (로컬 또는 CVM)
- ✅ **GitHub Actions 동작 시연**: 코드 push → CVM 자동 배포 로그 보여주기
- ✅ **로그인 페이지 데모**: 로그인 성공 → 대시보드(빈 쉘) 진입
- ✅ **Health 엔드포인트**: `/health` 200 OK 확인
- ⚠️ **AI 채팅은 Sprint 2 예정**: "다음주 완성됩니다" 설명
- ⚠️ **회계 자동화는 5월 중순 목표**: 뼈대 완성 후 즉시 착수

**Key Message**: "견고한 설계에 투자하여 향후 5개 팀 모듈을 안정적으로 올릴 기반을 만들고 있음"

---

## 12. Migration Path (A/C에서 B로 역전환 시 참고용)

> 본 프로젝트는 B로 시작하지만, 미래에 다른 프로젝트에서 참고할 수 있도록 기록.

C → B 점진 마이그레이션 전략:
1. 기존 `services/` 폴더를 `use_cases/`로 이름 변경
2. 순수 로직을 `domain/` 레이어로 추출
3. DB 접근 코드를 `infrastructure/repositories/`로 분리
4. 레이어별 테스트 작성

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-16 | Initial draft — Option B Clean Architecture 선택, 9 세션 구성 | TK101 (junki7853) |
