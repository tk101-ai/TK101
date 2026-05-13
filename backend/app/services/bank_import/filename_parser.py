"""파일명 → FilenameMeta 추출.

대상 패턴 예시 (실제 샘플):
- ``TK101( 국민  097601-04-277245 )_2026-1사분기.xlsx``
- ``TK101( 기업 231-132137-04-011 )_2021-3사분기.xlsx``
- ``TK101 (신한  100-037-970355 기보 강남구청대출 )_2026-1사분기 .xlsx``
- ``TK101 ( 우리 외화 1081-901-067637)_2026-1사분기.xlsx``
- ``TK101( KEB하나 외화  274-910006-25838 )_2020-2사분기.xlsx``

엣지:
- ``~$`` 임시파일 → None
- ``.xlsx`` 가 아닌 파일 → None
- 패턴 매칭 실패 → None (워크북 메타로 fallback)
"""
from __future__ import annotations

import os
import re

from app.services.bank_import.adapter import FilenameMeta

# 은행명(한글/영문/표기변형) → 내부 키
BANK_NAME_MAP: dict[str, str] = {
    "KB국민": "kbstar",
    "KB": "kbstar",
    "국민": "kbstar",
    "kbstar": "kbstar",
    "기업": "ibk",
    "IBK기업": "ibk",
    "IBK": "ibk",
    "ibk": "ibk",
    "농협": "nonghyup",
    "NH농협": "nonghyup",
    "NH": "nonghyup",
    "nh": "nonghyup",
    "신한": "shinhan",
    "shinhan": "shinhan",
    "우리": "woori",
    "woori": "woori",
    "하나": "hana",
    "KEB하나": "hana",
    "hana": "hana",
}

# 라벨 키워드 (account_label 추출). "외화 ", "대출 " 형태로 은행명 뒤에 붙음.
_LABEL_KEYWORDS = (
    "외화",
    "대출",
    "기보보증대출",
    "기보 강남구청대출",
    "신탁MMT",
    "퇴직연금신탁",
    "퇴직연금DC",
)

# 메인 패턴: TK101 ( {은행명/라벨} {계좌번호} ... ) _ {YYYY}-{Q}사분기
# 계좌번호: 3~6자리 hyphen 구조 (KB: 097601-04-277245, IBK: 231-132137-04-011,
# 농협: 301-0199-7114-01, 신한: 140-012-448332, 우리: 1005-204-597759 or 1005204597759,
# 하나: 274-910006-25838)
_FILENAME_PATTERN = re.compile(
    r"TK101\s*\(\s*(?P<bank_block>.+?)\s*\)\s*_?\s*(?P<year>\d{4})-(?P<quarter>\d)사분기",
    re.IGNORECASE,
)

# 계좌번호: hyphen 포함, 3그룹 이상 또는 10자리 이상 연속
_ACCOUNT_PATTERN = re.compile(r"(\d{2,6}(?:-\d{2,7}){1,4}|\d{10,18})")


def _normalize_account_number(raw: str) -> str:
    """공백 제거, 하이픈 유지."""
    return raw.strip()


def _extract_bank_and_label(bank_block: str) -> tuple[str | None, str, str | None]:
    """``"기업 외화 480-045493-56-00017"`` → (bank_key, raw_name, "외화").

    Returns (bank_key, raw_bank_name, account_label).
    """
    # 계좌번호 제거 후 남는 토큰을 분석
    no_account = _ACCOUNT_PATTERN.sub("", bank_block)
    tokens = [t for t in no_account.split() if t]

    if not tokens:
        return None, bank_block.strip(), None

    bank_key: str | None = None
    raw_bank_name = tokens[0]
    # 첫 토큰부터 매칭, 한글+영문 prefix 결합도 시도 (KEB하나)
    for i in range(min(2, len(tokens)), 0, -1):
        candidate = "".join(tokens[:i])
        if candidate in BANK_NAME_MAP:
            bank_key = BANK_NAME_MAP[candidate]
            raw_bank_name = candidate
            tokens = tokens[i:]
            break
    if bank_key is None:
        # 단일 토큰만 매칭 시도
        if tokens[0] in BANK_NAME_MAP:
            bank_key = BANK_NAME_MAP[tokens[0]]
            raw_bank_name = tokens[0]
            tokens = tokens[1:]

    # 남은 토큰 = account_label 후보
    label_tokens: list[str] = []
    for tok in tokens:
        if tok in _LABEL_KEYWORDS or any(kw in tok for kw in _LABEL_KEYWORDS):
            label_tokens.append(tok)
        else:
            # 라벨로 보이지 않는 자유 텍스트도 일단 포함 (예: "기보 강남구청대출")
            label_tokens.append(tok)

    account_label = " ".join(label_tokens).strip() if label_tokens else None
    return bank_key, raw_bank_name, account_label


def parse_filename(filename: str) -> FilenameMeta | None:
    """파일명 → FilenameMeta. 실패 시 None.

    파일 잠금용 ``~$`` 임시파일이나 ``.xlsx`` 가 아닌 파일은 즉시 None.
    """
    if not filename:
        return None

    base = os.path.basename(filename).strip()
    if base.startswith("~$"):
        return None
    if not base.lower().endswith(".xlsx"):
        return None

    m = _FILENAME_PATTERN.search(base)
    if not m:
        return None

    bank_block = m.group("bank_block")
    year = int(m.group("year"))
    quarter = int(m.group("quarter"))

    acc_m = _ACCOUNT_PATTERN.search(bank_block)
    if not acc_m:
        return None

    account_number = _normalize_account_number(acc_m.group(1))
    bank_key, raw_bank_name, account_label = _extract_bank_and_label(bank_block)
    if bank_key is None:
        return None

    return FilenameMeta(
        bank_key=bank_key,
        raw_bank_name=raw_bank_name,
        account_number=account_number,
        account_label=account_label,
        year=year,
        quarter=quarter,
    )
