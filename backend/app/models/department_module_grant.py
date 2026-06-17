from sqlalchemy import Column, String

from app.models.base import Base, TimestampMixin


class DepartmentModuleGrant(TimestampMixin, Base):
    """부서 → 허용 모듈 grant. 관리자가 런타임 편집(기존 하드코딩 매핑 대체).

    행 존재 = 해당 부서에 해당 모듈 허용. admin role 은 이 테이블과 무관하게
    전 모듈 접근(registry.get_user_modules). registry 가 기동 시 메모리 캐시로 로드.
    """

    __tablename__ = "department_module_grants"

    department = Column(String, primary_key=True)
    module = Column(String, primary_key=True)
