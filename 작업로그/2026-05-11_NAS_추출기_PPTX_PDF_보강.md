# 2026-05-11 — NAS 추출기 PPTX/PDF 보강 (무료, v0.8.0)

| 항목 | 값 |
|------|-----|
| 날짜 | 2026-05-11 |
| 브랜치 | main |
| 목적 | 야간 풀 재인덱싱 전에 무료 범위의 텍스트 추출 회수율 향상 |
| 제외 항목 | Haiku 요약 backfill (유료 $15~20, 사용자 요청으로 미사용) |

---

## 1. 배경

저번주(5/4~5/8) v0.7.0 한글/엑셀 추가 + Haiku 요약 backfill 코드는 들어갔지만
실제 라이브에서 트리거 자체가 실패. 오늘 밤부터 내일 아침까지 풀 재인덱싱 예정.

회수율 향상 여지가 큰 두 가지 추출기를 보강한다:
- PPTX: `shape.text`만 보던 단순 경로 → 그룹/노트/표/차트까지 평탄화
- PDF: pdfminer 빈 결과 → pdfplumber fallback (MIT 라이선스)

---

## 2. 변경 파일

| 파일 | 변경 |
|---|---|
| `backend/app/services/nas_search/text_extractor.py` | PPTX 그룹 재귀/노트/표/차트, PDF pdfplumber fallback |
| `backend/pyproject.toml` | `pdfplumber>=0.11` 추가 |

---

## 3. PPTX 보강 상세

### Before
```python
for shape in slide.shapes:
    text = getattr(shape, "text", None)
    if text:
        parts.append(text)
```

### After
- `_collect_pptx_shapes(shapes, parts)` 재귀 헬퍼 분리
- 그룹 shape(`shape_type == 6`) → `shape.shapes`로 재귀 진입
- 표(`has_table`) → `shape.table.rows`/`cells` 순회
- 차트(`has_chart`) → 카테고리 + 시리즈 이름만 (값은 노이즈)
- 발표자 노트(`slide.notes_slide.notes_text_frame.text`) — 슬라이드별로 별도 append
- 도형 1개 실패가 전체를 죽이지 않게 항목별 try/except

### 회수 기대치
디자인 PPT는 대부분 그룹 도형 사용. v0.6.7 DB 진단에서 본문 추출 실패 7,648개(63.5%) 중
PPTX 비중이 큰 폴더(MARKETING/00_채널별 소개서, 04_업무 메뉴얼)에서 의미있는 회수 예상.

---

## 4. PDF fallback 상세

### Before
```python
return (pdf_extract(path) or "").strip()
```

### After
1차 pdfminer.six → 결과 비어있으면 2차 pdfplumber.
- pdfplumber는 내부적으로 pdfminer.six를 쓰지만 레이아웃 분석 경로가 달라
  표/다단 레이아웃 회수율이 올라간다.
- OCR이 아니므로 이미지 PDF는 여전히 빈 결과 (Phase 4 OCR은 별건).
- 라이선스: MIT (PyMuPDF AGPL 회피).

---

## 5. 오늘 밤 실행 계획 (SSH 작업)

```bash
ssh ubuntu@43.155.202.112
cd /home/ubuntu/actions-runner/_work/TK101/TK101

# 1. 코드 최신화 확인 (자동 배포가 끝났는지)
./scripts/healthcheck.sh

# 2. 진단 — 진행 중인 인덱싱 / 마지막 트리거 실패 흔적
ps -ef | grep -E "nas-index" | grep -v grep
docker compose logs --tail=50 backend | grep -iE "error|trace" | tail -20

# 3. 오늘 밤 풀 재인덱싱 (Tier 1 + Tier 2 일부)
#    --full로 v0.7.0 HWP/HWPX/XLSX + v0.8.0 PPTX/PDF 보강 결과 모두 다시 색인
nohup ./scripts/nas-index.sh "MARKETING/04_업무 메뉴얼 (★)" --full > /tmp/full-manuals.log 2>&1 &
echo "PID: $!"

# 4. 떠나기 전 확인
sleep 30
tail -10 /tmp/full-manuals.log
disown -a
exit
```

내일 아침:
```bash
tail -50 /tmp/full-manuals.log
docker exec tk101-postgres psql -U tk101 -d tk101 -c "
SELECT file_type,
       count(*) FILTER (WHERE last_error IS NULL AND indexed_at IS NOT NULL) AS clean,
       count(*) FILTER (WHERE last_error IS NOT NULL) AS failed,
       count(*) AS total
FROM nas_files
GROUP BY file_type ORDER BY total DESC;"
```

---

## 6. Haiku 백필 보류 사유

- 비용: 12K 파일 × Haiku 4.5 ≈ $15~20
- 사용자 요청: "유료가 아닌 무료로 우선 진행"
- 보강 효과는 큰 편이지만, 본문/파일명/요약 3중 매칭의 마지막 한 겹.
  먼저 본문 회수율을 올리고(이번 push), 그래도 부족하면 그때 검토.

---

## 7. 검증 시나리오 (내일 아침)

- 라이브 검색에서 `회사 소개서`, `위챗 광고`, `매뉴얼` 검색
- DB에서 `last_error IS NULL AND indexed_at IS NOT NULL` 비율이 36.5% → 60%+ 목표
- PPTX 비중이 큰 폴더에서 chunk 수 증가 추세 확인:
  ```sql
  SELECT count(*) FROM nas_text_chunks tc
  JOIN nas_files f ON f.id = tc.file_id
  WHERE f.path LIKE '%MARKETING/00%' AND f.name ILIKE '%.pptx';
  ```
