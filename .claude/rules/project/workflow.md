# 표준 작업 플로우 (기능 1개 개발)

> CLAUDE.md §4에서 참조. 새 기능 개발 시작할 때 이 파일을 여세요.
> **이 13단계는 Sprint 1 이후 모든 기능에 반복 적용됩니다.**

## 전체 플로우 개요

```
A. 기획→설계 (bkit 주도)       B. 준비→구현 (ECC 주도)        C. 검증→배포 (bkit 주도)
  1-3단계                         4-7단계                         8-13단계
```

## A. 기획 → 설계 (bkit 주도)

### 1. Plan 생성

```
/bkit:pdca plan <feature>
```

- Checkpoint 1: 요구사항 확인 질문에 답변
- Checkpoint 2: 세부 명세 질문에 답변
- 출력: `docs/01-plan/features/<feature>.plan.md`

### 2. Design 생성

```
/bkit:pdca design <feature>
```

- Checkpoint 3: 3가지 아키텍처 옵션 중 선택
- **본 프로젝트는 항상 Option B (Clean Architecture) 선택**
- 출력: `docs/02-design/features/<feature>.design.md`

### 3. (선택) UI 목업 — 복잡한 UI만

```
/bkit:phase-3-mockup <feature>
```

- 단순 CRUD 백오피스는 스킵 가능
- 사용자 플로우가 3단계 이상이면 목업 권장

## B. 구현 준비 → 구현 (ECC 주도)

### 4. 구현 계획 세부화

```
/plan <feature>
```

- Design을 기반으로 파일별 작업 순서 수립
- 의존성 그래프 확인 (Domain → Infra → App → Pres 순)

### 5. 테스트 먼저 작성

```
/tdd <feature>
```

**작성 순서 (Clean Architecture 기준):**

1. **L0 Domain 단위 테스트** — Entity 메서드, Domain Service 순수 로직
2. **L1 API 테스트** — 각 라우터 엔드포인트 (status, schema, error cases)
3. **L2 UI 액션 테스트** — 페이지별 상호작용 (Playwright)
4. **L3 E2E 시나리오** — 다중 페이지 플로우

### 6. 코드 작성 (레이어 순서 엄수)

**Backend 순서:**

```
1. Domain
   - entities/ 추가/수정
   - repositories/ 인터페이스 정의
   - (필요시) value_objects/, services/ 인터페이스

2. Infrastructure
   - database/models/ SQLAlchemy 모델
   - repositories/ 구현체 (sqlalchemy_xxx_repository.py)
   - alembic revision 생성

3. Application
   - use_cases/ 비즈니스 흐름

4. Presentation
   - api/v1/schemas/ Pydantic
   - api/v1/routers/ FastAPI 라우터
   - api/v1/deps.py (필요시 새 DI)
```

**Frontend 순서:**

```
features/<feature>/
  1. types/      — Domain 타입
  2. api/        — 백엔드 호출 함수
  3. services/   — 비즈니스 흐름
  4. hooks/      — React 상태 관리
  5. components/ — UI 컴포넌트
  6. app/<path>/page.tsx — 페이지 조립
```

- ECC `python-reviewer` / `typescript-reviewer`가 자동으로 각 저장 시 리뷰
- 레이어 위반 시 차단됨 (Import 규칙)

### 7. 구현 진행 추적

```
/bkit:pdca do <feature> --scope <module>
```

- 세션 1개당 scope 1개 권장
- Do 완료 후 체크리스트 확인

## C. 검증 → 배포 (bkit 주도)

### 8. QA 실행

```
/bkit:qa-phase <feature>
```

- L1/L2/L3 테스트 실행 및 리포트
- FAIL 시 `/bkit:pdca iterate`로 자동 개선 루프

### 9. 갭 분석

```
/bkit:pdca analyze <feature>
```

- Design vs 구현 코드 비교
- 목표: Match Rate 90%+
- < 90%면 `iterate`, ≥ 90%면 `report`

### 10. 자동 개선 (필요시)

```
/bkit:pdca iterate <feature>
```

- Gap list 기반 자동 수정
- 최대 5회 반복 후 Check 재실행

### 11. 완료 보고서

```
/bkit:pdca report <feature>
```

- PRD→Plan→Design→구현→결과 종합
- Success Criteria 최종 체크

### 12. 배포

```
git add .
git commit -m "feat: <feature>"
git push
```

- GitHub Actions가 자동으로 CVM에 배포
- 배포 로그: GitHub Actions 탭 확인

### 13. 문서 아카이브

```
/bkit:pdca archive <feature> --summary
```

- PDCA 문서들을 `docs/archive/YYYY-MM/<feature>/`로 이동
- `--summary` 옵션: 메트릭만 `.bkit/state/pdca-status.json`에 보존

## 세션 분할 원칙

- **1 세션 = 1 scope** (Design §11.3 Session Guide 참조)
- 세션 시작 시 반드시 CLAUDE.md + 해당 Design 문서 재로드
- Do 단계는 `--scope <module>`로 제한하여 컨텍스트 집중
- **세션당 실제 코드 변경 300~500줄 권장** (초과 시 다음 세션으로)

## 단계 건너뛰기 규칙

| 단계 | 건너뛰기 허용? | 조건 |
|------|:----------:|------|
| 1. Plan | ❌ | 절대 스킵 금지 |
| 2. Design | ❌ | 절대 스킵 금지 |
| 3. 목업 | ✅ | 단순 CRUD는 스킵 |
| 4. /plan | ✅ | Design이 충분히 상세하면 스킵 |
| 5. /tdd | ❌ | 80% 커버리지 목표 — 스킵 금지 |
| 6. 코드 작성 | - | 필수 |
| 7. /bkit:pdca do | 🟡 | 단순 수정은 스킵 가능 |
| 8. /bkit:qa-phase | 🟡 | 뼈대 완성 전 스킵 가능, 이후 필수 |
| 9. /bkit:pdca analyze | ❌ | 필수 |
| 10. /bkit:pdca iterate | ✅ | 갭이 ≥ 90%면 스킵 |
| 11. /bkit:pdca report | 🟡 | 작은 기능은 스킵 가능 |
| 12. git push | ❌ | 필수 |
| 13. archive | 🟡 | 주요 feature만 아카이브 |
