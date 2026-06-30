# PLAN — NAS 이미지/미디어 임베딩 (VLM 캡션 방식)

작성 2026-06-30 · 상태: **계획 (파일럿부터)** · 대상: `/home/ubuntu/tk101-rag` (적재) + `tk101-dev` (vision 호출·검색)

## 1. 목적
NAS 이미지(주로 MARKETING 고객사 디자인/사진, **jpg ≥20,000+**)를 검색 가능하게 만든다. 접근 = **VLM 캡션 → 텍스트 임베딩**(오너 결정). 멀티모달(CLIP) 대신 기존 텍스트 파이프라인 재사용.

## 2. 현황 (조사 2026-06-30)
**완전 텍스트 전용.** 이미지 확장자는 수집 대상(`parse.py:28 DOC_EXT`)에 없고, 문서 내부 박힌 이미지(고객사 PPT 차트·인포그래픽)도 **100% 손실**(`text_extractor.py:117-216`, `parse.py:68-74`는 텍스트만).

**있는 것 (재사용 가능)**
- **그릇 예약됨**: `config.py:62 COLLECTION_IMAGE="docs_image"`, payload `modality` 값에 `image_visual` 정의. (컬렉션 생성 함수만 미구현)
- **vision 호출 인프라 존재** (`tk101-dev`): `playground/attachments.py` — 이미지→base64 data URL(`:203-241`), OpenAI호환 vision content 빌더 `build_user_content`(`:253-299`), `VISION_MODELS`(gpt-5-chat, gemini-2.5/3.x …, `:78-90`). `tencent_aigc_client.py` 게이트웨이(8개 공급자) + **docgen은 Claude 직접(call_claude)** 도 가능.
- 텍스트 임베딩/청킹/적재/멱등 파이프라인 그대로 캡션 적재에 사용.
- OCR 경로(`modality=image_ocr`) 이미 존재(스캔 PDF→텍스트).

**없는 것 (신규 필요)**
- `docs_image` 컬렉션 실제 생성 + 이미지 수집 워커(`DOC_EXT`에 이미지 추가 또는 별도 iter).
- VLM 캡션 → 임베딩 배치 잡.
- 문서 내부 이미지 추출(`shape.image.blob`, `page.get_images()`).
- 검색측 `docs_image` 조회·병합.

> ⚠️ 정정: 조사 중 인용된 "텐센트 게이트웨이 전모델 401 블로커"는 **옛 정보**. 어제(#143) 토큰 활성지연 코드문제로 판명·해결됨. 단 **어떤 vision 모델이 게이트웨이로 실제 통과되는지는 미확인**(docgen 메모상 gpt-5-chat만 200) → **vision 공급자는 Claude Haiku 직접 호출 권장**(신뢰성).

## 3. 설계 (캡션→임베딩)
```
이미지 파일 → (Pillow 다운스케일) → base64 data URL → VLM(캡션 프롬프트: 한국어로
  무엇이 담겼는지·텍스트·브랜드·장면 묘사) → 캡션 텍스트
→ 캡션을 기존 Qwen3 파이프라인으로 임베딩 → docs_image 컬렉션 upsert
  payload: modality=image_visual, path, doc_id, dept, caption(text), ...
```
검색: 텍스트 쿼리 → 같은 Qwen3로 임베딩 → docs_text + docs_image 동시 조회 → 병합. (의미공간 동일 = 캡션도 2560d라 한 인코더로 양쪽 검색 가능.)

## 4. 단계
| 단계 | 내용 | 비용/승인 |
|---|---|---|
| **P0 정확 센서스** | NAS-direct(`find` over SSH, sshfs 아님)로 이미지 전수 카운트·용량 → 실제 N과 비용 산정 | 무비용 |
| **P1 파일럿** | `docs_image` 컬렉션 생성 + **소규모(예: COMPANY 865장 또는 고객사 1곳)** 캡션→임베딩→검색 품질·비용 실측 | 소액 LLM |
| **P2 본 적재** | (오너 비용 승인 후) 독립 이미지 파일 전체 | ⚠️**대량 LLM = §2 승인** |
| **P3 문서 내부 이미지** | pptx/pdf/docx 박힌 이미지 추출→캡션→임베딩 (디자인 PPT 가치 큼) | ⚠️대량 |
| **검색 통합** | `bridge.search_relevant_chunks`가 `docs_image` 옵션 조회·병합, 출처에 썸네일/경로 | 무비용 |

## 5. 비용 (개략, P0 후 확정)
이미지 N × VLM 캡션 1회. 저가 vision(Haiku/Gemini Flash) ~ $0.001–0.005/장 가정 → **2만 장 ≈ $20–100, 10만 장 ≈ $100–500**. **P0 센서스로 N 확정 후 P2 착수 전 오너 승인.** P1 파일럿은 소액.

## 6. 의사결정
- 접근: **VLM 캡션→임베딩** (확정).
- vision 공급자: **Claude Haiku 직접** 권장(게이트웨이 vision 미검증) — 단가/품질 P1에서 비교.
- 스코프: 독립 파일 먼저(P2), 문서 내부 이미지(P3)는 별도.
- 영상(mp4): 희소 → 후순위(키프레임 캡션은 v2).

## 7. 다음 액션
**P0 센서스 + P1 파일럿**부터(소액). 결과로 품질·단가 확인 후 P2 대량 적재는 오너 비용 승인.
