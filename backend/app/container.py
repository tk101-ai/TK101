"""DI 컨테이너 — 의존성 팩토리 모음.

Design Ref: §9.4 DI 방법 — FastAPI Depends + 팩토리 함수

이 파일은 도메인 모듈이 추가될 때마다 확장됨.
현재(Sprint 0)는 스켈레톤만 존재.

예시 (Sprint 1+):
    async def get_user_repository(
        session: AsyncSession = Depends(get_db_session),
    ) -> UserRepository:
        return SqlAlchemyUserRepository(session)

    async def get_authenticate_user_use_case(
        user_repo: UserRepository = Depends(get_user_repository),
        hasher: PasswordHasher = Depends(get_password_hasher),
        jwt_provider: JWTProvider = Depends(get_jwt_provider),
    ) -> AuthenticateUserUseCase:
        return AuthenticateUserUseCase(user_repo, hasher, jwt_provider)
"""
