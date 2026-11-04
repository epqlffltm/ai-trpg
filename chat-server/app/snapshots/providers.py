# chat-server/app/snapshots/providers.py

"""
설정(SNAPSHOT_PROVIDER)으로 그림 provider 를 고른다(#983). 모양은 ai_core 의 ImageProvider 다.

  - off: 장면 그림을 만들지 않는다(503 snapshot_unavailable). 기본값이다
  - gemini: Nano Banana(GEMINI_API_KEY 가 있어야 한다). 운영의 것이다
  - comfyui: 이 서버 곁의 ComfyUI 의 Stable Diffusion(COMFYUI_URL, COMFYUI_CHECKPOINT). 개발·시험용이다
  - fake: 정해 둔 그림(테스트용)
가격표 이름은 이 서버의 머리(chat)와 image 뒤에 그림 모델의 이름에서 점을 붙임표로 바꾼 것이다
(chat.image.gemini-nano-banana-2-1). 결제 서버는 서버마다 자기 머리의 가격표로만 홀드를 받는다
(billing-server/internal/httpapi/price_scope.go). 머리가 없으면 400 price.unknown 이다.
"""

import httpx
from ai_core.comfyui import ComfyUIProvider, ComfyUISettings
from ai_core.fake import FakeImageProvider
from ai_core.gemini_image import GeminiImageProvider
from ai_core.image_provider import ImageProvider

from app.billing.prices import PRICE_CODE_PREFIX
from app.core.config import Settings

# 가격표 이름의 앞. 이 서버의 머리 다음에 둔다
PRICE_PREFIX = f'{PRICE_CODE_PREFIX}.image.'


def price_code_of(model: str) -> str:
    """그림 모델의 가격표 이름. 점은 붙임표로 바꾼다(가격표 이름에 점을 쓰지 않는다)."""
    return f'{PRICE_PREFIX}{model.replace(".", "-")}'


def build_image_provider(settings: Settings, http: httpx.AsyncClient) -> ImageProvider | None:
    """설정의 그림 provider. 끄거나 키·체크포인트가 없으면 None(장면 그림을 만들지 않는다)."""
    kind = settings.snapshot_provider
    if kind == 'fake':
        return FakeImageProvider(model=settings.snapshot_model)
    if kind == 'gemini' and settings.gemini_api_key.get_secret_value():
        return GeminiImageProvider(
            http,
            settings.gemini_base_url,
            settings.gemini_api_key,
            settings.snapshot_model,
            timeout=settings.snapshot_timeout_seconds,
        )
    if kind == 'comfyui' and settings.comfyui_checkpoint:
        comfy = ComfyUISettings(checkpoint=settings.comfyui_checkpoint)
        return ComfyUIProvider(http, settings.comfyui_url, comfy, timeout=settings.snapshot_timeout_seconds)
    return None
