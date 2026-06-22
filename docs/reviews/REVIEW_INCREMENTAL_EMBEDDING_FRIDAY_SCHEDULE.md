# 증분 임베딩 파이프라인 리뷰 + 매주 금요일 18:00 스케줄(RunPod 서버리스) 설계

> 상태: **리뷰 + 설계 문서 (READ-ONLY)**. 코드 변경·임베딩 실행 없음. 오너 지시: 비긴급, 검토·문서화만.
> 작성일: 2026-06-22
> 대상: `/home/ubuntu/tk101-rag` (외부 파이프라인) + `/home/ubuntu/tk101-dev` (메인 앱) + Qdrant `docs_text`

---

## 0. 한눈에 (TL;DR)

- **현재**: 신규 문서 임베딩은 **수동**이다. cron/systemd timer **없음**(확인함). 사람이 `parse → build_records → index`를 `nohup`+`while-true` 재시도 스크립트로 돌린다.
- **증분 감지**: 진짜 "지난 실행 이후 NAS에 새로 추가된 파일" 델타 감지는 **없다**. 현재 멱등성은 (a) 파싱 단계 `.done`/`.manifest`, (b) 적재 단계 `.ckpt` 청크 카운터, (c) Qdrant point id = `uuid5(path#idx)` 덮어쓰기 — 세 가지로 "이미 처리한 건 다시 안 함"은 되지만, **새 파일만 골라내는 매니페스트는 없다**.
- **임베딩 실행처**: 문서(passage) 임베딩은 **RunPod GPU Pod의 vLLM**(`Qwen/Qwen3-Embedding-4B`, 2560-dim). 쿼리(query) 임베딩만 8090/백엔드 **호스트 CPU**로 전환됨(라이브 RunPod 의존 0). 즉 **새 문서 인덱싱 때만 GPU가 필요**하고, 그게 이번 금요일 잡의 핵심.
- **금요일 18:00 서버리스 설계의 핵심 결정**: RunPod(외부) → Qdrant(현재 `127.0.0.1:6333`, CVM 내부 전용)로 어떻게 **벡터를 안전하게 적재**할 것인가. 이게 단일 최대 설계 포인트다(아래 §6).

---

## 1. 현재 파이프라인 요약 (파일 경로 포함)

데이터 흐름: **NAS 파일 → 파싱 JSONL → 청크 레코드 JSONL → 임베딩 → Qdrant `docs_text`**

| 단계 | 파일 | 역할 | 증분/체크포인트 |
|---|---|---|---|
| 파싱(정식) | `/home/ubuntu/tk101-rag/pipeline/parse.py` | sshfs NAS root walk → 형식별 추출(pdf/docx/xlsx/pptx/hwp via LibreOffice/OCR) → `{path,ext,method,chars,size,mtime,text}` JSONL | `<out>.manifest`(1회 스캔 캐시), `<out>.done`(처리한 path 누적, 재시작 skip), `<out>.empty.jsonl`(스캔본→2차 OCR 패스) |
| 파싱(rsync 배치) | `/home/ubuntu/tk101-rag/pipeline/fetch_parse.py` | sshfs 랜덤액세스 회피용. NAS에서 작은 묶음씩 rsync로 당겨 로컬 16코어 파싱 후 삭제. 경로는 canonical(`/mnt/nas/...`)로 기록 | `<out>.done`, `<out>.deferred.jsonl`(--max-mb 초과 2차) |
| 청킹+레코드화 | `/home/ubuntu/tk101-rag/pipeline/chunk.py` + `build_records.py` | 구조기반 청킹(512토큰 목표, 80토큰 중첩 ≈15%), 분류메타(`/home/ubuntu/classify_final.jsonl`) basename 조인 → payload 부여 | point id=`uuid5(path#i)`, `file_hash`=본문 sha256[:16], `doc_id`=path sha1[:16] |
| 임베딩 클라이언트 | `/home/ubuntu/tk101-rag/pipeline/embed.py` | RunPod vLLM `/v1/embeddings`(OpenAI 호환)에 텍스트 배치 POST → 2560-dim 벡터. 차원 검증·지수백오프 재시도 | — |
| 적재(순차) | `/home/ubuntu/tk101-rag/pipeline/index.py` | 청크 64개씩 임베딩 → 256개씩 upsert(`wait=True`) → `.ckpt` 전진 | `<chunks>.ckpt`(커밋된 청크 수). `--restart` 안 주면 이어서 |
| 적재(병렬) | `/home/ubuntu/tk101-rag/pipeline/index_parallel.py` | 동일 결과물, WORKERS개 동시 임베딩 요청(GPU 가동률↑, ~2배). 윈도우(연속구간) 전부 적재 후에만 ckpt 전진 | 동일 `.ckpt` 포맷. Qdrant 32MB POST 한도 회피 위해 **256개씩** upsert |
| 컬렉션 생성 | `/home/ubuntu/tk101-rag/scripts/create_collections.py` | `docs_text` 2560-dim cosine + payload 인덱스 8종 | `--recreate` 시에만 삭제 |
| 설정(단일 소스) | `/home/ubuntu/tk101-rag/config.py` | 컬렉션명·차원·엔드포인트·payload 스키마 전부 여기 | — |

**운영 스크립트(모두 수동 `nohup`)**: `run_company_embed.sh`, `run_marketing_parallel.sh`, `run_marketing_resume.sh`, `run_company_recover.sh` 등. 공통 패턴:
- `until ping; sleep 120` 으로 **GPU(임베딩 서버) 켜질 때까지 대기**
- `while true; … sleep 60` **재시도 루프** — 배포가 Qdrant 컨테이너를 재시작시켜 호스트 잡의 `localhost:6333` 연결을 끊어 죽이는 함정([[embedding-jobs-ops]]) 때문. `.ckpt`로 재개.

**중요 운영 사실** (memory에서 확인):
- 배포(`docker compose up -d --build --force-recreate`)가 **Qdrant 재시작 → 호스트 임베딩 잡 크래시**. 재시도 루프 필수.
- Qdrant upsert POST **32MB 한도** → 2560-dim 벡터는 **256개씩** 끊어 upsert.
- 병렬화 상한 ~2배. 병목은 임베딩 동시성이 아니라 **윈도우별 upsert(`wait=True`) 직렬 배리어**.

---

## 2. 메인 앱 Qdrant는 어떻게 채워지나 / 스키마

- **메인 앱은 Qdrant를 읽기만 한다.** 적재는 전적으로 외부 `tk101-rag` 파이프라인이 담당(인앱 인덱서는 폐기됨 — `nas_files`/pgvector `embedding` 컬럼 죽음, [[session-2026-06-19]]).
- 백엔드 연결: `/home/ubuntu/tk101-dev/backend/app/config.py`
  - `qdrant_url`(기본 `http://qdrant:6333`, 같은 docker network의 `qdrant` 서비스)
  - `qdrant_collection_text = "docs_text"`
  - 검색 코드: `backend/app/services/nas_search/qdrant_search.py`, `query_embedder.py`(호스트 CPU Qwen3-4B), `bridge.py`, `reranker.py`(bge-reranker-v2-m3).
- **컬렉션**: `docs_text`, **2560-dim, cosine**.
- **payload 스키마** (`tk101-rag/config.py` PAYLOAD_FIELDS, point에는 `text`도 함께 저장):
  - 필수(★): `modality`(text/image_ocr/...), `doc_id`, `file_hash`, `confidential`
  - 기타: `dept`, `brand`, `year`, `is_archived`, `source_type`, `path`, `page`, `chunk_index`, `n_chunks`
  - payload 인덱스(필터용): `modality`, `doc_id`, `file_hash`, `dept`, `brand`, `year`(int), `is_archived`(bool), `confidential` — keyword 위주.
- **실측 분포(2026-06-19)**: `docs_text` points ≈ 1,598,749. dept facet: 마케팅 1,503,073 / RND 60,199 / 경영지원팀 21,709 / 신사업 13,358 / 마케팅본부 410(레거시).

---

## 3. 임베딩 실행처: 현재 상태

| 임베딩 종류 | 어디서 | 모델 | 비고 |
|---|---|---|---|
| **문서(passage) 임베딩** | **RunPod GPU Pod** (vLLM, `config.EMBED_API_URL` proxy.runpod.net:8000) | `Qwen/Qwen3-Embedding-4B` → 2560-dim | LLM(14B)과 GPU 동시 상주 불가 → 임베딩 단계에만 4B만 올림. **이번 금요일 잡의 대상.** |
| **쿼리(query) 임베딩** | **호스트 CPU** (8090 검색서버 + 백엔드) | sentence-transformers Qwen3-4B bf16, instruct prefix+normalize | RunPod 라이브 의존 제거됨([[session-2026-06-19]]). mmap warmup 필요(콜드 33s→웜 0.3s). |

**핵심**: 라이브 RunPod 소비자=0. **RunPod는 새 문서 인덱싱 때만 잠깐 띄운다.** vLLM 임베딩 경로(`embed.py`)는 보존됨. 즉 금요일 잡은 "그때만 GPU 띄워 델타 임베딩 후 적재하고 끄는" 패턴에 자연스럽게 맞는다 — **서버리스(필요할 때만 과금)와 궁합이 좋다.**

---

## 4. NAS 신규 파일 감지 (증분) — 현재의 공백과 전략

### 현재 한계
- `parse.py`의 `.manifest`는 **전체 root를 1회 스캔한 스냅샷**일 뿐, "지난 금요일 이후 새로 생긴 파일"을 알지 못한다. `.done`은 처리완료 path 집합 → **재시작 skip용**이지 델타 감지용이 아니다.
- 같은 path를 다시 돌리면 `uuid5(path#i)`로 덮어쓰기 되어 중복은 없지만, **전체 root를 매번 walk+파싱**하면 비용이 폭증한다(마케팅만 150만 청크).
- `parse.py`는 파싱 결과에 `mtime`, `size`를 이미 기록한다 → **델타 판정 재료는 이미 있다**(쓰이지 않을 뿐).

### 제안: 임베딩 매니페스트(상태 파일) 도입
지속 상태 파일 `embedded_manifest.jsonl`(예: `data/state/embedded_manifest.jsonl`, NAS나 Qdrant payload로도 재구성 가능):

```
{ "path": "/mnt/nas/MARKETING/...", "mtime": 1718000000, "size": 12345,
  "file_hash": "ab12…",  "doc_id": "…", "n_chunks": 7, "embedded_at": "2026-06-20T18:05Z" }
```

금요일 잡의 **델타 선정 로직**:
1. NAS root를 `find -printf '%T@\t%s\t%p'`로 **NAS-direct**(sshfs 랜덤액세스 금지, 사양서 §5) 스캔 → 현재 파일 목록(path, mtime, size).
2. 매니페스트와 비교:
   - path가 매니페스트에 **없음** → **신규**.
   - path는 있으나 **mtime/size 변경** → **수정**(재파싱·재임베딩, 멱등 덮어쓰기).
   - (선택) 매니페스트에 있으나 NAS에 없음 → **삭제** → Qdrant에서 `doc_id` 필터로 제거.
3. 델타만 `fetch_parse.py`로 파싱 → `build_records.py` → `index_parallel.py`.
4. 적재 성공분만 매니페스트에 append/갱신.

> **대안(매니페스트 없이)**: Qdrant `docs_text`에서 `path` payload distinct 집합을 추출해 "이미 임베딩된 path"로 삼고, NAS find 결과와 차집합. 단 mtime 변경 감지는 안 됨(payload에 mtime 없음 → `file_hash`로 내용변경은 잡지만 그러려면 일단 파싱해야 함). **→ payload에 `mtime` 추가를 권장**(스키마 확장, 재적재 불필요·신규분부터 채움).

### 생성 문서 출력 소스(docwork 타이인)
- 사양서의 자동화 ③ "문서작업"은 생성물을 만든다. 현재 백엔드 출력 루트: `form_filler_output_root = /var/lib/form_filler/outputs`(`tk101-dev/backend/app/config.py`). 이건 컨테이너 로컬이라 NAS가 아니다.
- **권고**: 임베딩 대상으로 삼으려면 생성물을 **NAS의 지정 폴더**(예: `/mnt/nas/_generated/` 또는 `/mnt/nas-rw/playground/...` 계열)에 저장하도록 출력 경로를 합의하고, 그 폴더를 금요일 잡의 root 중 하나로 포함. (현재 PRD/코드에 docwork→NAS 저장 경로는 **미확정** → 오픈 퀘스천 §8.)

---

## 5. 금요일 18:00 스케줄 설계 (RunPod 서버리스)

### 5.1 트리거 방식 — 3안

| 안 | 트리거 | 장점 | 단점 |
|---|---|---|---|
| **A. CVM cron이 RunPod를 깨움** (권장) | CVM의 systemd timer(`Fri 18:00`)가 RunPod **Serverless `/run` 엔드포인트**를 HTTPS 호출 | 델타 선정·NAS 스캔을 **CVM(NAS sshfs 보유)에서** 수행, 서버리스엔 "임베딩할 텍스트"만 보냄. Qdrant 접근도 CVM 안에서 끝낼 수 있음(§6 push 모델) | CVM이 스케줄 주체(CVM 다운 시 미실행 — 모니터링 필요) |
| B. RunPod 자체 스케줄 | RunPod의 cron/schedule 기능으로 워커가 금요일에 자동 기동 | CVM 의존 없음 | 워커가 NAS·Qdrant에 **외부에서** 접근해야 함(보안·네트워킹 부담↑). NAS sshfs 마운트를 서버리스에 들고 가기 어려움 |
| C. 외부 스케줄러(GH Actions cron 등) | GitHub Actions `schedule: cron`이 RunPod 엔드포인트 호출 | CVM 독립 | 시크릿(RunPod API key) 외부 보관, GH Actions cron 지연 편차 큼 |

**권장 = A**. 이유: 델타 감지에 NAS 접근이 필요한데, NAS는 CVM에 sshfs로 마운트돼 있고(`/mnt/nas`, `/mnt/nas-rnd`, `/mnt/nas-rw`), RunPod 서버리스에 sshfs 마운트를 재현하는 것은 취약·복잡하다. **CVM이 오케스트레이터, 서버리스는 순수 임베딩 워커**로 역할 분리.

systemd timer 예시(설계만, 미적용):
```
# /etc/systemd/system/tk101-embed.timer
[Timer]
OnCalendar=Fri 18:00
Persistent=true   # CVM 꺼져 있었으면 다음 부팅 때 보충 실행
```

### 5.2 역할 분담 — "얇은 워커" 패턴 (권장)

```
[CVM cron Fri 18:00]
  └─ scan_delta.py  (NAS-direct find vs embedded_manifest → 신규/수정 파일 목록)
  └─ fetch_parse.py (델타만 rsync→로컬 파싱→ data/parsed/delta_YYYYMMDD.jsonl)
  └─ build_records.py (→ data/chunks/delta_YYYYMMDD.jsonl, 청크 레코드: id/text/payload, 벡터 없음)
  └─ RunPod Serverless /run 호출:
        input = { chunks_batch: [ {id, text, payload}, … ] }  (텍스트만 전송, 원본파일 미전송 — 사양서 원칙)
        worker: Qwen3-Embedding-4B 로 임베딩 → 2560-dim 벡터 반환 (또는 직접 Qdrant push, §6)
  └─ index_parallel 로직: 반환 벡터 + payload → Qdrant upsert(256개씩, uuid5 멱등) → .ckpt/manifest 전진
```

이렇게 하면 **서버리스 워커는 GPU 임베딩만** 담당(NAS도 Qdrant도 직접 안 봄) → 콜드스타트 최소, 보안 표면 최소. 청킹·델타·적재는 검증된 기존 CVM 코드를 재사용.

> **대안(두꺼운 워커)**: 서버리스가 청킹+임베딩+Qdrant push까지 다 함. 장점은 CVM 부하 0. 단점은 서버리스에서 NAS 접근(델타·파싱 입력)이 필요 → §6 보안·네트워킹 부담이 워커 쪽으로 옮겨감. **비권장.**

### 5.3 체크포인트 / 멱등 (재실행 안전)

- 기존 자산 그대로 활용: point id=`uuid5(path#i)` → **재실행해도 덮어쓰기**(이중 임베딩되어도 결과 동일, 중복 point 없음).
- `delta_YYYYMMDD.jsonl.ckpt`로 윈도우 단위 전진 → 잡이 죽어도(서버리스 타임아웃·Qdrant 끊김) 재개.
- 매니페스트는 **upsert 성공분만** 갱신 → 중간 실패 시 다음 주에 다시 델타로 잡힘(누락 없음).
- 서버리스 호출 자체에 **idempotency key**(예: `delta_YYYYMMDD#window_k`)를 부여하면 재시도 시 중복 과금/중복 처리 방지.

---

## 6. ★핵심 설계 결정 — RunPod(외부) → Qdrant 도달성 / 보안

**제약**: Qdrant는 `tk101-qdrant` 컨테이너로 **`127.0.0.1:6333`/`6334`만 바인딩**(docker-compose.yml에 명시, 외부 노출 금지 — 사양서 §5 "❌ Qdrant를 외부에 두지 말 것", audit M-11). 저장은 `/home/ubuntu/qdrant_storage` bind mount. RunPod 서버리스는 **외부 네트워크**라 기본적으로 `localhost:6333`에 도달 못 한다.

선택지:

| 방식 | 설명 | 평가 |
|---|---|---|
| **6-A. Push 모델 (권장)** | 서버리스는 **벡터만 CVM에 반환**(임베딩 결과 JSON). **Qdrant upsert는 CVM이 수행**(이미 `localhost:6333` 접근 가능). Qdrant를 외부에 전혀 노출 안 함. | ✅ 보안 표면 0 증가. 기존 사양서 원칙 부합. 단점: 벡터(2560×4B≈10KB/청크)를 서버리스→CVM으로 되받아야 함(대역폭, 응답 페이로드 큼 → 윈도우 단위 분할 응답). **이게 §5.2 얇은 워커와 정확히 일치.** |
| 6-B. WireGuard/터널로 Qdrant 노출 | CVM↔RunPod 워커 간 WireGuard 메시 → 서버리스가 사설 IP로 `6333` 접근 후 직접 upsert | 서버리스 인스턴스마다 WG peer 등록/회수가 까다롭고(동적 IP), 짧은 수명 워커에 과함. 운영 복잡. **비권장(서버리스엔).** |
| 6-C. Qdrant Cloud / 외부 Qdrant | 외부 관리형 Qdrant로 이전 | 사양서 "벡터DB 내부보관" 원칙 위반. **금지.** |
| 6-D. mTLS 리버스 프록시로 6333 한정 노출 | Qdrant 앞에 nginx mTLS, RunPod 클라이언트 인증서로만 upsert 허용 | 인증서 관리·방화벽(ufw 미설정 상태, audit 잔여)·API key 회전 필요. 노출 표면 생김. 6-A로 피할 수 있으면 불필요. |

**결정: 6-A Push 모델.** 서버리스는 "텍스트 in → 벡터 out" 순수 함수로 두고, **Qdrant 쓰기는 CVM 내부에서만** 일어나게 한다. 이러면:
- Qdrant `127.0.0.1` 바인딩 유지(외부 노출 0).
- RunPod에 줄 시크릿은 **임베딩 모델 가중치 접근(HF) 정도**, Qdrant 자격증명 불필요.
- 전송되는 건 **텍스트 청크(요청)+벡터(응답)** 뿐 → 원본 파일 외부 미전송 원칙 유지.
- 단, **벡터 응답 페이로드가 큼** → 윈도우(예 384청크)당 ~4MB. RunPod serverless 응답 크기 한도 확인 필요(오픈 §8). 한도 걸리면 윈도우 더 잘게 + S3/임시저장 경유 또는 6-D로 폴백 검토.

---

## 7. 비용 / 운영 (cold start, throughput, retry, monitoring)

- **콜드스타트**: 서버리스는 매 기동마다 컨테이너+모델 로드. Qwen3-Embedding-4B 가중치 ≈ 8GB(bf16) → 콜드 수십 초~분. **금요일 1회 배치**라 콜드스타트를 작업 전체로 amortize하면 무시 가능. RunPod **FlashBoot/active worker** 옵션은 상시 과금이라 주1회 잡엔 비권장(콜드 감수가 더 쌈).
- **처리량**: 기존 GPU Pod 실측 순차 ~14청크/s, 병렬 ~26~29청크/s. 상한 ~2배(병목=윈도우 upsert 직렬 배리어). **얇은 워커(6-A)면 upsert가 CVM이라 GPU는 임베딩만 풀가동** → 병목이 옮겨감(CVM upsert가 율속). 주간 델타 규모가 작으면(수천~수만 청크) **수 분 내 완료** 예상.
- **GPU 동시상주**: 14B LLM과 4B 임베딩 GPU 동시 불가는 **단일 Pod 제약**. 서버리스 워커는 임베딩 전용 이미지로 독립 기동하므로 이 문제 없음(LLM 안 올림).
- **실패/재시도**:
  - 서버리스 호출 단위 재시도(지수백오프, 기존 `embed.py` 패턴 그대로).
  - 윈도우 단위 `.ckpt` → 중간 실패 재개.
  - 매니페스트는 성공분만 → 미완 델타는 다음 주 재포착.
  - **배포-중-Qdrant-재시작 함정**([[embedding-jobs-ops]]): 금요일 18:00에 배포가 겹치지 않게 하거나, CVM upsert 루프를 `while-true` 재시도로 감쌀 것.
- **모니터링**:
  - 잡 종료 시 결과를 통합 알림(이메일/메신저 ops 스킬)로: 델타 N파일/M청크, 실패 K, Qdrant points 증가분.
  - `corpus-stats`(백엔드 `GET /api/nas/corpus-stats` = Qdrant 청크수+dept facet)로 적재 전후 카운트 검증.
  - systemd timer `Persistent=true` + `OnFailure=` 알림 유닛으로 미실행/실패 감지.
  - RunPod 사용량(분·$)을 잡 로그에 기록 → 주간 비용 추적.

---

## 8. 오픈 퀘스천 (오너 확인 필요)

1. **델타 규모**: 매주 NAS에 실제로 추가/수정되는 문서량은? (서버리스 1회 비용·시간 산정의 핵심. 수천 청크면 콜드스타트가 비용의 대부분.)
2. **docwork 생성물 저장 경로**: 자동화 ③ 문서작업 산출물을 임베딩 대상에 포함하려면 **NAS 어느 폴더**에 저장할지 확정 필요. 현재 `form_filler_output_root=/var/lib/form_filler/outputs`(컨테이너 로컬, NAS 아님). 이걸 NAS 폴더로 바꿀지, 별도 export 스텝을 둘지?
3. **payload `mtime` 추가**: 수정 파일 재임베딩 감지를 위해 Qdrant payload(및 매니페스트)에 `mtime` 추가 OK? (신규분부터 채우면 됨, 재적재 불필요.)
4. **삭제 동기화**: NAS에서 지워진 문서를 Qdrant에서도 제거할지? (지금은 누적만. 제거하려면 매니페스트 diff → `doc_id` 필터 delete.)
5. **6-A 벡터 응답 페이로드 한도**: RunPod Serverless 응답 크기/타임아웃 한도 확인. 한도 초과 시 윈도우 더 잘게 vs 임시 객체저장 경유 vs 6-D(노출) 중 선택.
6. **트리거 주체**: CVM systemd timer(권장) vs RunPod 자체 스케줄 vs GH Actions cron — CVM 가용성에 의존해도 되는지(주1회 미실행 리스크 허용 범위).
7. **금요일 18:00 배포 충돌**: 같은 시간대 배포(Qdrant 재시작)와 겹칠 가능성 — 잡 윈도우를 배포 윈도우와 분리할지.
8. **서버리스 vs 기존 Pod 재사용**: 기존 RunPod GPU Pod를 그대로 스케줄로 켜고 끄는 것(이미 vLLM 경로 검증됨)과, 신규 Serverless 엔드포인트 구축 중 어느 쪽? 전자는 구축 비용 0(스크립트만), 후자는 진짜 "필요할 때만 과금"이지만 핸들러 코드·이미지 구축 필요.

---

## 9. 권고 요약

1. **얇은 워커 + Push 모델(6-A)**: 서버리스는 임베딩만, 델타·청킹·Qdrant적재는 CVM. → Qdrant `127.0.0.1` 유지, 보안 표면 0.
2. **CVM systemd timer `OnCalendar=Fri 18:00`**가 오케스트레이터(권장 트리거 A).
3. **증분 매니페스트 도입**: NAS-direct find(mtime/size) vs `embedded_manifest.jsonl` 차집합으로 델타만. payload에 `mtime` 추가.
4. **기존 멱등·체크포인트 자산 재사용**: `uuid5(path#i)`, `.ckpt`, 256개 upsert, `while-true` 재시도.
5. **저렴한 시작안**: 우선 기존 RunPod Pod를 스케줄로 켜고/끄는 방식(스크립트만, 구축 0)으로 금요일 잡을 돌려보고, 비용이 문제면 그때 진짜 Serverless 핸들러로 전환(오픈 §8.8).

> 본 문서는 검토·설계만 담는다. 코드·임베딩·인프라 변경은 오너 승인 후 별도 PR.
