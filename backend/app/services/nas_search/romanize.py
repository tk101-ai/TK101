"""한글 → 로마자(국립국어원 RR 근사) 변환.

목적: 문서엔 고객사명이 영문(예: HUIDA)으로 적혀 있는데 사용자는 한글(후이다)로
검색하는 경우, 한글 쿼리 토큰을 로마자로도 키워드 매칭해 연결한다.
음절 단위 단순 변환(자모 결합 규칙 미적용) — substring 키워드 매칭엔 충분.
"""

_INITIAL = [
    "g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s",
    "ss", "", "j", "jj", "ch", "k", "t", "p", "h",
]
_MEDIAL = [
    "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa",
    "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i",
]
_FINAL = [
    "", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "p", "l",
    "l", "p", "l", "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t",
]


def romanize_hangul(text: str) -> str:
    """한글 음절을 RR 근사 로마자로. 비한글 문자는 그대로 둔다."""
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if 0xAC00 <= cp <= 0xD7A3:
            idx = cp - 0xAC00
            final = idx % 28
            medial = (idx // 28) % 21
            initial = idx // 28 // 21
            out.append(_INITIAL[initial] + _MEDIAL[medial] + _FINAL[final])
        else:
            out.append(ch)
    return "".join(out)


def has_hangul(text: str) -> bool:
    return any(0xAC00 <= ord(c) <= 0xD7A3 for c in text)
