"""은행별 어댑터.

각 모듈은 ``BaseBankAdapter`` 를 상속한 클래스를 1개씩 노출한다.
새 은행을 추가하면 ``registry.ADAPTERS`` 에 등록한다.
"""
from app.services.bank_import.adapters.hana import HanaAdapter
from app.services.bank_import.adapters.ibk import IBKAdapter
from app.services.bank_import.adapters.kbstar import KBStarAdapter
from app.services.bank_import.adapters.nonghyup import NonghyupAdapter
from app.services.bank_import.adapters.shinhan import ShinhanAdapter
from app.services.bank_import.adapters.woori import WooriAdapter

__all__ = [
    "HanaAdapter",
    "IBKAdapter",
    "KBStarAdapter",
    "NonghyupAdapter",
    "ShinhanAdapter",
    "WooriAdapter",
]
