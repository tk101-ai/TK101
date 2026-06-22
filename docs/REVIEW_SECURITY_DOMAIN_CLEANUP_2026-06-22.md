# 검토 보고서 — 보안 / 도메인 / 파일정리 (2026-06-22)

> **메타**
> - 작성일: 2026-06-22
> - 성격: 멀티에이전트 병렬 조사 결과(읽기 전용). **이 문서 작성 시점에 서버는 아무것도 변경하지 않음.**
> - 서버: `VM-1-17-ubuntu` · Tencent Cloud CVM(서울) · 공인 IP `43.155.202.112`
> - 목적: 나중에 검토하며 실행 여부를 결정하기 위한 참고 문서
> - 관련: [PRD_DOCWORK_UNIFY_2026-06-22.md](PRD_DOCWORK_UNIFY_2026-06-22.md)

---

## PART 1 — 네트워크 보안 감사 + 외부접속 권고

### 1.1 현재 상태 (실측)

호스트 **ufw는 비활성** → **Tencent Cloud 보안그룹(SG)만이 유일한 방화벽**. 전 구간 HTTP(TLS 없음).

| 포트 | 서비스 | compose 바인딩 | 외부 도달 | 비고 |
|---|---|---|---|---|
| 22 | SSH | host | **열림** | 비밀번호+root 로그인 허용 (위험) |
| **8080** | frontend nginx (`/api/`,`/n8n/`) | `0.0.0.0:8080` | **열림** | 메인 앱 입구, HTTP only |
| **3000** | **open-webui** | `0.0.0.0:3000` | **열림** | ⚠️ CRITICAL (아래) |
| 8000 | backend FastAPI | `127.0.0.1:8000` | 닫힘 | localhost 바인딩 (양호) |
| 8001 | backend-dev | `0.0.0.0:8001` | 차단(SG가 막음) | 0.0.0.0 바인딩 — SG만 의존 |
| 5678 | n8n | `127.0.0.1:5678` | 닫힘 | localhost + nginx auth 게이트 |
| 3001 | langfuse | `127.0.0.1:3001` | 닫힘 | 양호 |
| 5432 | postgres | `127.0.0.1:5432` | 닫힘 | 양호 |
| 6333/4 | qdrant | `127.0.0.1:6333-4` | 닫힘 | 양호 |

양호: postgres·qdrant·langfuse·n8n·운영 backend 모두 `127.0.0.1` 바인딩 → 외부 비도달.

### 1.2 발견된 위험 (우선순위)

| 등급 | 내용 |
|---|---|
| 🔴 **CRITICAL** | **open-webui(:3000) 인터넷 공개 + 회원가입(`ENABLE_SIGNUP=true`)** — 누구나 가입 가능. ANTHROPIC 키 쥔 LLM 게이트웨이 노출. 가입자는 `pending` 게이트로 일부 제한되나, 공개 가입 엔드포인트 자체가 노출. |
| 🟠 **HIGH** | SSH 22 = 비밀번호+root 로그인 허용, **fail2ban 없음** → 브루트포스 표적 |
| 🟡 **MEDIUM** | backend-dev(:8001) `0.0.0.0` 바인딩 — SG 오설정 시 즉시 공개. CORS가 `http://43.155.202.112:5173` 허용 |
| 🟡 **MEDIUM** | 전 구간 HTTPS 없음 — 로그인 JWT 포함 평문 전송 |
| 🟢 LOW | Vite dev 서버 `0.0.0.0:5173` 호스트 가동(SG 밖이라 외부 비도달이나 느슨) |

### 1.3 오너의 3개 아이디어 판정

**A. WireGuard + 직원별 키 — ★ 정답 (생각보다 간단)**
- 커널 모듈 이미 존재(`wireguard.ko`). 설치 1줄.
- UDP 포트 1개만 SG에 열고 8080/3000/22를 **인터넷에서 닫음**. VPN 연결 후에만 앱 접근. 오프라인 시 서버는 인터넷에 "어둡게" 보임.
- 직원 온보딩: 키쌍 생성 → 서버 설정 3줄 추가 → `.conf`(또는 QR) 전달 → 무료 WireGuard 앱에 2분 임포트. 회수=3줄 삭제. CA/비밀번호 불필요.
- 공수: 초기 1~2시간, 직원당 5분.
- 장점: 최강 보안, 앱 변경 0, **모든 서비스(SSH·n8n·langfuse·qdrant) 동시 보호**. 단점: 직원이 VPN 토글 필요, 키 목록 관리.

**B. NAT 출구 IP 화이트리스트 — 사무실 전용엔 유효, "외부접속"엔 부적합**
- 지금 SG가 사실상 이걸 하는 중.
- **함정: 사무실 IP가 고정인가?** 한국 오피스 회선은 보통 **유동 IP**(라우터 재부팅·임대갱신 시 변경). ISP에 고정 IP 여부 확인 필요(보통 유료 옵션).
- 유동이면: IP 바뀌는 날 **전원 잠김**, 그 사이 옛 IP를 타인이 물려받을 위험.
- **결정적 한계**: 오너의 목표는 직원의 **외부(집·이동·모바일)** 접속 → IP가 제각각·가변이라 화이트리스트 불가. B는 사무실 전용만 해결.
- WireGuard와 결합: B 불필요해짐. 앱 포트는 누구에게도 안 열고 **WireGuard UDP 포트만** 문으로. 사무실/외부 모두 VPN 연결.

**C. 기타 심플+강력 하드닝**
- 불필요 공개포트 닫기(무료, 즉효): SG에서 **3000(open-webui)** 공개 제거. 8000/8001/5678 등 계속 닫힌 상태 유지.
- TLS: 외부접속 켤 때 HTTPS 종단 — **Cloudflare**(무료, 오리진 IP 은닉+TLS+WAF+레이트리밋) 또는 **Caddy**(자동 Let's Encrypt). 도메인 필요(PART 2).
- SSH 하드닝(15분): `PasswordAuthentication no`, `PermitRootLogin no`(키 우선 확인), **fail2ban** 설치. WireGuard 후엔 22를 VPN 전용으로.

### 1.4 권고 순서 (보안이득 ÷ 공수)

**지금 당장(오늘·~30분, 새 도구 0 — 라이브 노출 차단)**
1. SG에서 **포트 3000(open-webui) 공개 차단** + 계정 생성 후 `ENABLE_SIGNUP=false`.
2. **SSH 하드닝**: fail2ban 설치, 비밀번호·root 로그인 비활성(키 동작 먼저 확인).
3. **backend-dev 8001 바인딩**을 `127.0.0.1:8001`로(compose 수정).

**그다음(외부접속 안전 개방, ~2시간 — 진짜 해결책)**
4. **WireGuard 설치**, 직원당 키 1개·`.conf` 배포. SG엔 **WireGuard UDP 포트만** 개방.
5. **8080·SSH 22를 인터넷에서 닫고** VPN 뒤로.
6. **호스트 ufw 켜기**(기본 차단 + WireGuard/established 허용) — SG 단독 의존 탈피.

**선택(VPN 없는 공개 웹접속도 원할 때)**
7. 도메인 + **Cloudflare를 8080 앞에**(무료: TLS·IP은닉·WAF·레이트리밋). SG를 Cloudflare IP 대역으로 제한. n8n/langfuse/qdrant/open-webui는 VPN 전용 유지.

> **B 최종 판정**: 사무실 고정 IP 확인 시 *임시 사무실 전용*으로만. 외부/로밍은 못 풀고 유동 IP에 취약 → **WireGuard(A)가 대체·권장**.

---

## PART 2 — 도메인 / HTTPS 옵션

### 2.1 현재 상태 (실측)
- 프런트 nginx: 호스트 **8080→컨테이너 80**, `listen 80;`만 — **HTTP 전용**. certbot/Caddy/443 일절 없음.
- **80/443은 SG가 차단, 8080만 열림** ← 모든 권고의 방향을 결정하는 핵심.
- 현재 접속: `http://43.155.202.112:8080/` (raw IP+포트).

### 2.2 도메인을 꼭 사야 하나 — HTTPS가 진짜 이유
- **raw IP로는 신뢰받는 인증서 발급 불가**(Let's Encrypt 등 공인 CA는 이름 필요). → 브라우저 "안전하지 않음" 경고.
- **이름이 생기는 순간** Let's Encrypt/Cloudflare TLS가 풀려 `https://이름/` + 자물쇠.
- **회사가 이미 `tk101global.com` 보유**(이메일 도메인) → **추가 구매 0원**, 서브도메인 `app.tk101global.com` 하나만 추가하면 됨. (먼저 보유·관리 위치 확인 권장)

### 2.3 무료로 "이름" 쓰는 방법 비교 (2026)

| 옵션 | 즉시성 | 신뢰 HTTPS | 인바운드 포트 개방 | 평가 |
|---|---|---|---|---|
| sslip.io / nip.io | 즉시 | 80/443 개방 필요, 와일드카드✗ | **필요(현재 막힘)** | 실효성 낮음 |
| DuckDNS | 5분, 무료 | LE DNS-01 가능(포트 불필요) | **접속용 443은 개방 필요** | 견고하나 인증서 자동화 직접 구성 |
| **Cloudflare Tunnel** | 15~30분 | **자동 제공** | **불필요(아웃바운드 전용)** | TK101에 최적합. 단 Cloudflare에 도메인 1개 등록 필요 |
| TryCloudflare | 즉시(도메인 불필요) | 자동 | 불필요 | URL 랜덤 → 테스트 전용 |
| ngrok 무료 | 즉시 | 자동 | 불필요 | URL 변동·제한 → 상시용 부적합 |

### 2.4 지금 당장 가능한가 — 최단 경로
**가능.** 두 갈래:
- **80/443 못 여는 경우(현재 기본)** → **Cloudflare Tunnel**이 유일하게 깔끔. cloudflared가 서버→Cloudflare **아웃바운드만** 만들어 `localhost:8080`을 `https://app.도메인/`으로 노출. 인바운드 0, 공인 IP 은닉.
- **SG에서 80/443 열 수 있으면** → DuckDNS+Let's Encrypt 등도 가능(단 오리진 IP 노출).

### 2.5 권고: Cloudflare Tunnel + (보유한) 회사 도메인 서브도메인
이유: 80/443이 막힌 현 환경에서 **포트 0개 개방 + HTTPS 자동 + 오리진 IP 은닉**(요청한 "도메인 뒤 숨기기")을 동시에 충족. 소규모·심플+견고에 최적.

**구체 단계(대략)**
1. `tk101global.com`(또는 신규 도메인)을 **Cloudflare에 추가**(네임서버 위임, 무료 플랜).
2. 서버에 `cloudflared` 설치 → `tunnel login` → `tunnel create tk101`.
3. ingress 라우팅: `app.tk101global.com` → `http://localhost:8080`.
4. `cloudflared`를 systemd 상시 가동 → 직원 `https://app.tk101global.com/` 접속.
5. (권장) **Cloudflare Access**로 회사 이메일 도메인만 로그인 허용.

> ⚠️ **주의**: 앱 업로드 한도 `client_max_body_size 220m`인데 **Cloudflare 무료 플랜은 요청 100MB 제한** → 큰 파일 업로드(문서 업로드 기능과 직결)는 사전 테스트 필요. 큰 파일 상시 필요 시 유료 플랜 또는 업로드만 VPN 경유 검토.

### 2.6 한국 특이사항
- 도메인은 Cloudflare Registrar(원가)/Namecheap 권장. `.com` ≈ $10/년. 가비아도 가능하나 갱신가·영어콘솔 측면에서 글로벌+Cloudflare 조합이 단순.
- `.kr`/`.co.kr`은 국내 등록기관 필요. 내부용엔 `.com` 서브도메인이 가장 단순.

---

## PART 3 — 파일 정리 (삭제 후보 조사, 보고 전용)

> 루트 `/dev/vda2` 493G 중 **162G 사용 / 311G 여유(35%)** — **디스크 압박 없음**. 아래는 안전 회수 가능 목록. **자동 삭제 안 함 — 검토 후 사람이 실행.**

### 3.1 절대 건드리면 안 됨 (검증 완료)
- `/home/ubuntu/qdrant_storage`(18G) — **라이브** tk101-qdrant 바인드마운트.
- `/home/ubuntu/tk101-rag` — **실행 중**(PID uvicorn `:8090` 로컬 임베딩 서버, cwd=tk101-rag). 코드 디렉토리 보존. `data/`(5.6G)는 임베딩 소스 → NEEDS CONFIRM.
- `/home/ubuntu/tk101-dev` — 라이브(backend-dev가 마운트). `node_modules`/`__pycache__` 유지.
- `actions-runner/_work/...` — 배포 레포(바인드마운트). 활성 러너 + 2.335.1 보존.
- 도커 명명 볼륨 7개 전부 LINKS=1(사용 중). **고아 볼륨 없음.**

### 3.2 회수 후보 (크기 내림차순)

| # | 경로 | 크기 | 정체 | 위험 | 제안 명령(사람이 실행) |
|---|---|---|---|---|---|
| 1 | docker build cache | **21 GB** | 6~7주 된 빌드캐시 | 🟢 SAFE | `sudo docker builder prune -f` |
| 2 | docker dangling `<none>` 이미지 | **~30–40 GB** | 옛 빌드 다수(컨테이너 0) | 🟢 SAFE | `sudo docker image prune -f` |
| 3 | `~/.cache/huggingface` | 7.6 GB | 호스트 HF 캐시(도커 볼륨과 별개) | 🟡 CONFIRM | 삭제 시 콜드스타트 재다운로드 |
| 4 | `tk101-rag/data` | 5.6 GB | 임베딩 파이프라인 중간물 | 🟡 CONFIRM | 라이브 서비스 소속 — 확인 후 |
| 5 | `/var/log/journal` | 1.1 GB | systemd 저널 | 🟢 SAFE | `sudo journalctl --vacuum-size=200M` |
| 6 | `actions-runner/{bin,externals}.2.334.0` | 671 MB | 구버전 러너(심링크는 2.335.1) | 🟢 SAFE | `rm -rf .../{bin,externals}.2.334.0` |
| 7 | `~/.cache/ms-playwright` | 631 MB | Playwright 브라우저 | 🟡 CONFIRM | 호스트 e2e 안 쓰면 삭제 |
| 8 | `~/.cache/pip` | 383 MB | pip 캐시 | 🟢 SAFE | `pip cache purge` |
| 9 | `parse_env` | 282 MB | 독립 venv(PDF 파싱) | 🟡 CONFIRM | rag 파이프라인 연관 확인 |
| 10 | `actions-runner/...2.333.1.tar.gz` | 214 MB | 러너 설치 tarball(이미 설치됨) | 🟢 SAFE | `rm ...tar.gz` |
| 11 | `/var/log/btmp*` | 121 MB | 실패 로그인 기록(브루트포스로 비대) | 🟢 SAFE | logrotate 처리 |
| 12 | `/tmp/gh_*`, `/tmp/gh.tgz` | 62 MB | gh CLI 잔여 | 🟢 SAFE | `rm -rf /tmp/gh_* /tmp/gh.tgz` |
| 13 | `/tmp/mkt_*` | 35 MB | NAS 마케팅 작업 스크래치 | 🟢 SAFE | `rm /tmp/mkt_*` |
| 14 | `/home/ubuntu/tk101-dev-nas` | 21 MB | **낡은 레포 사본**(6/17, 참조 없음 검증) | 🟢 SAFE | `rm -rf /home/ubuntu/tk101-dev-nas` |
| 15 | `_diag`, `/tmp` 기타 스크래치 | <30 MB | 진단/테스트 잔여 | 🟢 SAFE | 임의 삭제 |

### 3.3 회수 합계 (등급별)
- 🟢 **SAFE: ~53–63 GB** — 대부분 **#2 dangling 이미지(~30–40G) + #1 빌드캐시(21G)**. 최고효율·최저위험: `docker image prune -f` + `docker builder prune -f`.
- 🟡 **CONFIRM: ~14.4 GB** — 호스트 HF캐시(7.6G)·rag/data(5.6G)·playwright(631M)·parse_env(282M).
- 🔴 **금지**: 3.1 전부.

> 주의: dangling 이미지 회수량은 레이어 공유로 인해 합산보다 실제 적게 빠질 수 있음.

---

## 부록 — 실행 주체 구분

**승인 시 내가 서버에서 실행 가능**
- docker SAFE prune(~50GB) + 3.2의 SAFE 항목 정리(tk101-dev-nas 등)
- 코드 수정+배포: backend-dev `127.0.0.1:8001`, open-webui `ENABLE_SIGNUP=false`
- WireGuard / cloudflared 설치·설정 초안

**오너 콘솔/계정 필요**
- Tencent Cloud SG: 3000 차단 / WireGuard UDP 포트 개방 / (선택)80·443
- Cloudflare: `tk101global.com` 추가 + Tunnel 로그인 + (권장)Access
- ISP: 사무실 고정 IP 여부 확인(아이디어 B 검토 시)
