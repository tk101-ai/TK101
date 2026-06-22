"""메타 엔드포인트 — provider/모델 chip, 미디어 모델 카탈로그. 로그인만 필요."""
from __future__ import annotations

from fastapi import Depends

from app.models.user import User
from app.dependencies import get_current_user
from app.schemas.playground import (
    PlaygroundMediaModelOption,
    PlaygroundProviderMeta,
)
from app.services.playground import PROVIDER_CHIPS
from app.services.playground.tencent_aigc_media import IMAGE_MODELS, VIDEO_MODELS

from ._common import make_subrouter

router = make_subrouter()


@router.get("/providers", response_model=list[PlaygroundProviderMeta])
async def get_providers(
    user: User = Depends(get_current_user),
) -> list[PlaygroundProviderMeta]:
    return [PlaygroundProviderMeta.model_validate(p) for p in PROVIDER_CHIPS]


@router.get("/media-models")
async def list_media_models(
    user: User = Depends(get_current_user),
) -> dict[str, list[PlaygroundMediaModelOption]]:
    return {
        "image": [
            PlaygroundMediaModelOption(key=m["key"], label=m["label"], badge=m["badge"] or None)
            for m in IMAGE_MODELS
        ],
        "video": [
            PlaygroundMediaModelOption(key=m["key"], label=m["label"], badge=m["badge"] or None)
            for m in VIDEO_MODELS
        ],
    }
