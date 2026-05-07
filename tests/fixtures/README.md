# E2E 테스트 픽스처

E2E 자동 검증 시나리오에서 사용하는 샘플 자료 파일.

## 포함된 파일 (git-tracked)

가상의 디지털 마케팅 회사 "티케이101 마케팅"을 가정한 텍스트 자료.

| 파일 | 용도 |
|------|------|
| `sample_company_intro.txt` | 회사 소개·기본 정보 |
| `sample_marketing_report.txt` | 2025 캠페인 결과 보고서 |
| `sample_business_info.txt` | 사업·재무 요약 |

## 추가 권장 파일 (사용자 준비)

라이브 검증을 위해 실제 PDF 형식으로 다음 파일을 같은 폴더에 넣어주세요. 실제 사업과 무관한 더미 데이터 권장.

| 파일명 | 용도 | 크기 |
|--------|------|------|
| `sample_business_license.pdf` | 사업자등록증 (실제 양식) | < 1MB |
| `sample_marketing_report.pdf` | 마케팅 보고서 PDF | 1~5MB |
| `sample_large_doc.pdf` | 큰 파일 처리 검증 | > 5MB (40MB 이하) |

PDF 파일은 git에 commit하지 않습니다 (.gitignore 처리).

## 시나리오 매핑

자세한 사용 시나리오는 `작업로그/2026-05-07_e2e_시나리오.md` 참조.
