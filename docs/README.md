# docs/ — 문서 인덱스

저장소의 문서를 카테고리별 하위 폴더로 통합했다. 새 문서는 아래 분류에 맞는 폴더에 추가한다.

| 폴더 | 용도 |
|------|------|
| `prd/` | 제품 요구사항(PRD)·설계 스펙(SPEC)·프로젝트 설계(PROJECT_DESIGN)·대시보드 설계(DESIGN) |
| `reviews/` | 검토·감사 보고서(보안/도메인/검색품질 등), 분석 결과물(PDF 포함) |
| `ops/` | 운영·인프라 메모, 작업 우선순위·진행 리스트 |
| `worklogs/` | 날짜별 작업 로그 |
| `cost/` | 비용 시뮬레이션·논의 자료 |
| `decisions/` | 결정 기록: 커밋 컨벤션, 기술스택·환경 검토, ECC 병행 전략 등 |
| `assets/` | 원본 산출물(csv/txt/html 등 변환 전 자료) |
| `archive/` | 더 이상 쓰지 않지만 보존하는 옛 문서 |

## 참고

- `build_docs.py` — PDF 빌드 스크립트. `cost/` 등 하위 경로를 직접 참조하므로 파일 이동 시 경로를 함께 갱신한다.
- 루트의 `README.md`, `CLAUDE.md` 및 코드 인접 README(`frontend/`, `scripts/`, `n8n_workflows/`, `tests/`)는 제자리에 둔다.
