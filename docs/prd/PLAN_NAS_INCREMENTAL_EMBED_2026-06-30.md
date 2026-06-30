# PLAN — NAS 증분(신규/변경/삭제) 추가 임베딩

작성 2026-06-30 · 상태: **계획 (구현 보류 — 오너 지시)** · 대상 레포: **`/home/ubuntu/tk101-rag`** (검색 백엔드 tk101-dev 아님)

## 1. 목적
이미 적재된 NAS 코퍼스(현재 **1,598,749 청크 / 파일 ~80k**)에 **신규·변경 파일만 골라 추가 임베딩**하고, NAS에서 **삭제된 파일은 Qdrant에서 제거**하여 검색 인덱스를 NAS 실제 상태와 동기화한다.

## 2. 현황 (조사 2026-06-30)
파이프라인 4단계: `parse.py/fetch_parse.py → data/parsed/*.jsonl → build_records.py → data/chunks/*.jsonl → index.py/index_parallel.py → Qdrant docs_text`.

**있는 것 (재사용 가능)**
- **멱등 upsert**: point id = `uuid5(고정NS, "{path}#{chunk_index}")` (`build_records.py:21,109`) → 같은 경로 재임베딩 시 자동 덮어쓰기. **증분의 토대.**
- resume: parse `.done`(path)·`.manifest`, index `.ckpt`(청크 줄 수). 중단 재개는 견고.
- `file_hash = sha256(text)[:16]` 가 payload에 **생성은 되나 미사용**(`build_records.py:80`).
- parse 단계가 이미 파일 **mtime을 출력**(`parse.py:187,227`) — 비교 로직만 추가하면 됨.

**없는 것 (신규 필요)** ⚠️
1. **변경 감지**: `.done`이 path-only라 수정된 파일이 영영 스킵됨. mtime/size/hash 비교 부재.
2. **`file_hash` 활용**: 만들기만 하고 기존 값과 비교하는 코드 없음.
3. **삭제 동기화**: NAS에서 사라진 파일의 Qdrant 포인트 제거 로직 전무.
4. **꼬리 청크 정리**: 변경으로 청크 수가 **줄면** 옛 `chunk_index` 초과 포인트가 잔존(멱등 덮어쓰기는 같은 인덱스만 갱신).
5. **스케줄러**: cron/systemd timer 없음 — 전부 수동 `nohup`.

## 3. 설계
### 상태 저장 (manifest 승격)
`.done`(path 집합) → **상태맵** `path → {mtime, size, file_hash}` (JSON/SQLite). 적재 성공 시 갱신.

### 증분 파이프라인
```
incremental_scan.py:
  NAS 재스캔(현재 파일목록 + mtime/size)  vs  상태맵
  → NEW(상태맵 없음) / CHANGED(mtime|size 다름) / DELETED(NAS에 없음) 분류
  → (선택) CHANGED 후보만 file_hash 재확인으로 오탐 제거

증분 적재:
  NEW+CHANGED → 기존 parse→build_records→index 단계를 diff 집합에만 실행
  CHANGED → 적재 후 path별 (이전 n_chunks > 새 n_chunks)면 초과 chunk_index 포인트 delete
  DELETED → path 필터로 Qdrant 포인트 delete
  상태맵 갱신
```

### 단계
| 단계 | 산출물 | 난이도 |
|---|---|---|
| **P1 변경 감지** | `incremental_scan.py` (NEW/CHANGED/DELETED 리포트). 적재 없이 "무엇이 바뀌었나"부터 확보 | 낮음 |
| **P2 증분 적재** | diff 집합 parse→build→index 재사용 + 꼬리 청크 정리 + 삭제 동기화 + 상태맵 갱신 | 중 |
| **P3 운영 자동화** | systemd timer(주 1회 권장) + 배포 충돌 방지 락 + GPU 라우팅 | 중 |

## 4. 의사결정
- **GPU 전략** (RunPod 4B는 평소 off): **소량 일/주 증분 = 호스트 CPU 인코더**(쿼리용과 동일 Qwen3-Embedding-4B, sentence-transformers bf16, 수백 파일 OK) / **대량 백필만 RunPod 기동**. → 추천: CPU 우선, 임계치 초과 시 RunPod.
- **변경 감지 키**: mtime+size를 빠른 1차 게이트, CHANGED 후보만 file_hash로 2차 확인(오탐↓, I/O 절약).
- **주기**: 주 1회(systemd timer). 배포와 겹치지 않게 락.

## 5. 리스크
- 배포가 Qdrant 재시작시켜 잡 사망(과거 이슈, `--force-recreate` 제거로 완화됨) → 증분 잡도 재시도 루프로 감싸고 `.ckpt` 재개 패턴 유지.
- sshfs 재스캔 느림 → `fetch_parse.py`의 NAS-direct(SSH `find -printf`) 경로로 목록만 빠르게 수집 검토.
- 대량 CHANGED(폴더 통째 이동/리네임)는 path 변경=NEW+DELETED로 잡혀 재임베딩 비용 발생 → 리네임 감지는 v2.

## 6. 다음 액션
구현 보류 상태. 착수 시 **P1(변경 감지 리포트)** 부터 — 적재 비용 없이 "증분 규모"를 먼저 가시화.
