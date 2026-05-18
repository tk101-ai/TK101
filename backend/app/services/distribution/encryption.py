"""Fernet 기반 자격증명 암복호화 (T9 PRD 7-1).

용도:
- persona 의 ``api_id`` / ``api_hash`` 를 DB 저장 전에 암호화.
- 어드민 UI 에서 평문 입력 → 즉시 ``encrypt()`` 호출 → DB 에는 base64 토큰만 저장.
- 송신 워커에서 Telethon 클라이언트 생성 시 ``decrypt()`` 로 복호화.

키 관리:
- 마스터 키 (``settings.distribution_fernet_key``) 는 환경변수에만 두고 절대 commit X.
- 키 분실 시 모든 *_enc 컬럼 복호화 불가 → 재발급 + 재입력 필요.
- 키 회전: 새 키로 재암호화 후 ``MultiFernet`` 으로 점진 마이그레이션 (구현은 추후).

보안 고려:
- ``api_hash`` 노출 시 텔레그램 계정 도용 가능 → DB dump · 로그 · 에러메시지에서 절대 평문 노출 금지.
- 복호화 결과는 메모리 내에서만 사용하고, 함수 반환 시 호출자가 즉시 사용 후 폐기.
"""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)


class EncryptionError(RuntimeError):
    """암복호화 실패 — 키 미설정/잘못된 토큰/손상된 데이터."""


def _get_fernet() -> Fernet:
    """``settings.distribution_fernet_key`` 로 Fernet 인스턴스를 만든다.

    키가 없으면 ``EncryptionError`` 발생 — 페르소나 등록 시점에 명시적 실패.
    부팅 시점에 강제 검증하지 않는 이유: 다른 모듈 (재무·NAS) 만 쓰는 배포에서도
    앱이 정상 부팅되도록 lazy 검증.
    """
    key = settings.distribution_fernet_key
    if not key:
        raise EncryptionError(
            "distribution_fernet_key 가 설정되지 않았습니다. "
            ".env 에 base64 32-byte 키를 추가하세요. "
            "생성: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    # Fernet 은 bytes 입력만 받음. settings 는 str 이라 변환.
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise EncryptionError(
            "distribution_fernet_key 형식이 잘못됨 (base64 32-byte 필요)"
        ) from exc


def encrypt(plaintext: str) -> str:
    """평문 → base64 Fernet 토큰 문자열.

    빈 문자열은 그대로 빈 문자열 반환 (선택 입력 필드 대응).
    """
    if not plaintext:
        return ""
    fernet = _get_fernet()
    token_bytes = fernet.encrypt(plaintext.encode("utf-8"))
    # Fernet 결과는 이미 urlsafe-base64. str 로 변환만.
    return token_bytes.decode("ascii")


def decrypt(token: str) -> str:
    """base64 Fernet 토큰 → 평문 문자열.

    잘못된 토큰 / 만료 / 키 불일치 시 ``EncryptionError`` 발생.
    호출자는 절대 토큰/에러 상세를 로그에 남기지 말 것 (마스킹 책임).
    """
    if not token:
        return ""
    fernet = _get_fernet()
    try:
        plaintext_bytes = fernet.decrypt(token.encode("ascii"))
    except InvalidToken as exc:
        # 의도적으로 상세 노출 X — 공격자에게 힌트 안 줌.
        logger.warning("distribution encryption: invalid token")
        raise EncryptionError("암호화 토큰이 잘못되었거나 키가 불일치") from exc
    return plaintext_bytes.decode("utf-8")


def mask_hash(token: str, *, visible: int = 4) -> str:
    """UI 노출용 마스킹. 평문이 아닌 토큰 자체를 보여줄 일은 없지만 안전망.

    토큰 길이는 가변이라 base64 디코드 후 앞/뒤 몇 자만 보여줄 수도 있지만,
    그러면 길이 정보가 노출되므로 고정 마스크 사용.
    """
    if not token:
        return ""
    if len(token) <= visible * 2:
        return "*" * len(token)
    return f"{token[:visible]}...{token[-visible:]}"


def generate_key() -> str:
    """새 Fernet 키 생성 (운영자가 .env 초기화용으로 호출).

    ``Fernet.generate_key()`` 가 이미 urlsafe-base64 44-char ASCII 반환.
    이전 구현은 이중 인코딩 + 44자 자르기 버그가 있어 손상된 키를 만들었음.
    실제 배포에선 CLI 스크립트로 한 번 생성 후 .env 에 붙여넣는다.
    """
    return Fernet.generate_key().decode("ascii")
