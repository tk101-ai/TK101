# CVM 초기 세팅 가이드

> 이 문서는 **사용자가 CVM에 SSH 접속하여 1회 수동 실행**할 작업 모음입니다.
> GitHub Actions 자동 배포가 동작하기 전 필수 사전 작업.

**대상 환경**: Ubuntu 22.04 LTS, 사용자 `ubuntu`

---

## 전체 작업 흐름

```
[A] 로컬에서 SSH 키 생성 + CVM 접속
    ↓
[B] CVM에 Docker 설치
    ↓
[C] CVM에 배포 디렉터리 생성
    ↓
[D] 배포 전용 SSH 키 추가 (GitHub Actions가 쓸 키)
    ↓
[E] CVM 방화벽 포트 개방 (Tencent Cloud 콘솔)
    ↓
[F] GitHub Secrets 등록
    ↓
[G] main 브랜치 push → 자동 배포 확인
```

---

## [A] CVM 접속 준비

### 로컬에서 (Windows PowerShell)

이미 CVM SSH 접속이 되고 있다면 이 단계 스킵.

### CVM 접속 테스트

```bash
ssh ubuntu@<CVM_IP>
```

접속 성공하면 다음 단계로.

---

## [B] Docker + Docker Compose 설치

**CVM에서 실행:**

```bash
# 1. 기존 패키지 업데이트
sudo apt update && sudo apt upgrade -y

# 2. Docker 공식 설치 스크립트 실행
curl -fsSL https://get.docker.com | sudo sh

# 3. 현재 사용자(ubuntu)를 docker 그룹에 추가
sudo usermod -aG docker ubuntu

# 4. 세션 재시작 (중요!)
exit
```

재접속 후 확인:

```bash
ssh ubuntu@<CVM_IP>
docker --version          # Docker version 27.x.x 등
docker compose version     # Docker Compose version v2.x.x
docker run hello-world     # sudo 없이 실행되면 OK
```

---

## [C] 배포 디렉터리 생성

**CVM에서 실행:**

```bash
sudo mkdir -p /opt/tk101
sudo chown ubuntu:ubuntu /opt/tk101
cd /opt/tk101
pwd  # /opt/tk101 출력 확인
```

---

## [D] GitHub Actions 전용 SSH 키 생성

GitHub Actions가 CVM에 접속할 때 쓸 별도의 키 쌍을 만듭니다.
개인 SSH 키와 분리하여 보안 리스크 격리.

### 로컬(Windows PowerShell)에서 키 쌍 생성

```powershell
# 개인 키는 로컬에 저장, 공개 키는 CVM에 등록
ssh-keygen -t ed25519 -f $HOME\.ssh\tk101_deploy -C "github-actions-tk101" -N '""'
```

생성된 파일:
- `~/.ssh/tk101_deploy` — 개인 키 (GitHub Secrets에 등록할 것)
- `~/.ssh/tk101_deploy.pub` — 공개 키 (CVM에 등록할 것)

### 공개 키를 CVM에 등록

```powershell
# Windows PowerShell
Get-Content $HOME\.ssh\tk101_deploy.pub | ssh ubuntu@<CVM_IP> "cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

### 접속 테스트 (로컬에서)

```powershell
ssh -i $HOME\.ssh\tk101_deploy ubuntu@<CVM_IP> "echo 'deploy key OK'"
```

`deploy key OK` 출력되면 성공.

---

## [E] 방화벽 포트 개방 (Tencent Cloud 콘솔)

**작업 위치**: [Tencent Cloud 콘솔](https://console.cloud.tencent.com/cvm)

1. CVM 인스턴스 선택 → 보안 그룹(Security Group) 메뉴
2. "인바운드 규칙" 추가:

| 프로토콜 | 포트 | 소스 | 설명 |
|----------|------|------|------|
| TCP | 22 | 0.0.0.0/0 (또는 본인 IP) | SSH (이미 열려있을 것) |
| TCP | 3000 | 0.0.0.0/0 | Next.js frontend |
| TCP | 8000 | 0.0.0.0/0 | FastAPI backend |
| TCP | 80 | 0.0.0.0/0 | HTTP (Sprint 2 HTTPS에서 사용) |
| TCP | 443 | 0.0.0.0/0 | HTTPS (Sprint 2에서 사용) |

> **보안 권장**: 3000/8000 포트는 개발/초기 테스트용.
> Sprint 2 security scope 완료 후 80/443만 남기고 3000/8000은 내부망으로 제한.

---

## [F] GitHub Secrets 등록

**작업 위치**: GitHub 레포 → Settings → Secrets and variables → Actions → New repository secret

다음 시크릿들을 순서대로 추가:

| Secret Name | 값 | 설명 |
|-------------|------|------|
| `CVM_HOST` | `<CVM의 공인 IP>` | 예: `123.45.67.89` |
| `CVM_SSH_KEY` | `<tk101_deploy 파일 전체 내용>` | 개인 키. `-----BEGIN OPENSSH PRIVATE KEY-----`부터 `-----END OPENSSH PRIVATE KEY-----`까지 전부 |
| `POSTGRES_USER` | `tk101` | DB 사용자명 |
| `POSTGRES_PASSWORD` | `<강력한 비밀번호>` | 32자 이상 권장. `openssl rand -base64 32`로 생성 |
| `POSTGRES_DB` | `tk101` | DB 이름 |
| `JWT_SECRET_KEY` | `<32자 이상 랜덤 문자열>` | `openssl rand -base64 32` |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Claude API 키 |

### SSH 키 등록 시 주의사항

```powershell
# Windows PowerShell — 개인 키 내용 클립보드 복사
Get-Content $HOME\.ssh\tk101_deploy | Set-Clipboard
```

그 다음 GitHub Secret에 붙여넣기.
**개행 유지 필수** (`-----BEGIN`부터 `-----END`까지 모든 줄).

### 강력한 비밀번호 생성 예시

```powershell
# Windows PowerShell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

또는 CVM에서:

```bash
openssl rand -base64 32
```

---

## [G] 첫 자동 배포 테스트

### 로컬에서 main 브랜치에 push

```bash
cd "C:/Users/user/OneDrive/Desktop/TK101 AI"
git push origin main
```

### GitHub Actions 확인

1. GitHub 레포 → Actions 탭
2. 가장 최근 workflow run 클릭
3. Jobs 진행 확인:
   - ✅ backend-ci
   - ✅ frontend-ci
   - ✅ deploy (main push 시만)

### 배포 성공 시 확인

브라우저로 접속:

- `http://<CVM_IP>:8000/health` → `{"status":"ok",...}`
- `http://<CVM_IP>:3000` → TK101 AI Platform 랜딩 페이지
- `http://<CVM_IP>:8000/docs` → FastAPI Swagger UI

### 실패 시 디버깅

```bash
# CVM에 SSH 접속
ssh ubuntu@<CVM_IP>

cd /opt/tk101

# 컨테이너 상태
docker compose ps

# 전체 로그
docker compose logs

# 특정 서비스
docker compose logs backend
docker compose logs frontend
docker compose logs postgres

# 컨테이너 내부 진입
docker compose exec backend bash
```

---

## 트러블슈팅

### "Permission denied (publickey)"
- GitHub Secret `CVM_SSH_KEY`에 개인 키가 올바르게 등록되었는지 확인
- 공개 키가 CVM `~/.ssh/authorized_keys`에 있는지 확인
- `~/.ssh/authorized_keys` 권한이 600인지 확인

### "docker: permission denied"
- `sudo usermod -aG docker ubuntu` 실행했는지 확인
- 실행 후 **SSH 세션 재접속** 필수

### Backend health check 실패
- 포트 8000이 CVM 방화벽에서 열려있는지
- `docker compose logs backend`로 실제 에러 확인
- `.env` 파일이 `/opt/tk101/.env`에 있는지 (GitHub Actions가 생성)

### 포트 이미 사용 중 ("address already in use")
- CVM에 다른 프로세스가 포트 사용 중
- `sudo lsof -i :8000` 으로 확인 후 종료

---

## 롤백 (긴급 시)

```bash
# 로컬에서 이전 커밋으로 되돌려 push
cd "C:/Users/user/OneDrive/Desktop/TK101 AI"
git revert HEAD
git push origin main
# → GitHub Actions가 이전 버전으로 자동 재배포
```

또는 CVM에서 긴급 중지:

```bash
ssh ubuntu@<CVM_IP>
cd /opt/tk101
docker compose down
```

---

## 체크리스트

세팅 완료 후 아래 전부 체크되는지 확인:

- [ ] Docker 설치 완료 (`docker --version`)
- [ ] 배포 디렉터리 `/opt/tk101` 생성됨
- [ ] GitHub Actions 전용 SSH 키 쌍 생성됨
- [ ] 공개 키가 CVM `~/.ssh/authorized_keys`에 등록됨
- [ ] Tencent Cloud 방화벽 포트 3000/8000 열림
- [ ] GitHub Secrets 7개 모두 등록됨 (CVM_HOST, CVM_SSH_KEY, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, JWT_SECRET_KEY, ANTHROPIC_API_KEY)
- [ ] `git push origin main` 실행
- [ ] GitHub Actions 성공
- [ ] `http://<CVM_IP>:8000/health` 200 OK
- [ ] `http://<CVM_IP>:3000` 랜딩 페이지 렌더링

전부 체크되면 CI/CD 구축 완료.
