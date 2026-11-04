# shared/ai-core/src/ai_core/image_provider.py

"""
그림을 만드는 모델(image provider)의 모양(#983).

글을 쓰는 모델(ai_core/provider.py)과 모양을 따로 둔다.
받는 것(지시 글, 참고 그림)과 돌려주는 것(그림의 바이트)이 다르다.
쓰는 서버의 다른 코드는 이 모양만 안다. 외부 API(Gemini)와 로컬 모델(ComfyUI 의 Stable Diffusion)을 바꿔 끼운다.

  - 지시 글(prompt)은 쓰는 서버가 자기의 상태(장소, 시간대, 인물의 외형)로 만든다. 모델이 지어낸 상태를 쓰지 않는다
  - 참고 그림(references)은 인물의 얼굴과 차림을 맞추려고 넘기는 그림이다.
    받지 못하는 provider 도 있다(supports_references)
  - 실패는 글 모델과 같은 ProviderError 다. 공급자가 안전 규칙으로 거절했으면 refused, 그림 없이 끝났으면 no_image 다
    다시 시도할지, 돈을 돌려줄지는 부르는 쪽이 정한다
"""

import enum
from dataclasses import dataclass
from typing import Protocol

# 받은 그림 한 장의 크기의 상한(바이트). 넘으면 이상한 답으로 보고 버린다(malformed)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
# 거절의 이름. 공급자의 안전 규칙에 걸렸다
REFUSED = 'refused'
# 그림 없이 끝났다(거절인지 알 수 없다)
NO_IMAGE = 'no_image'
# 답의 모양이 틀렸다(그림을 읽을 수 없다, 너무 크다)
MALFORMED = 'malformed'
# 참고 그림을 받지 못하는 provider 에 참고 그림을 넘겼다
REFERENCES_UNSUPPORTED = 'references_unsupported'


class ReferenceKind(enum.StrEnum):
    """참고 그림의 쓰임. 인물(얼굴, 차림)을 맞추는 그림인가, 물건이나 배경인가."""

    CHARACTER = 'character'
    OBJECT = 'object'


@dataclass(frozen=True)
class ReferenceImage:
    """참고 그림 하나. data 는 그림의 바이트, mime_type 은 image/png 같은 형식이다."""

    data: bytes
    mime_type: str
    kind: ReferenceKind = ReferenceKind.CHARACTER


@dataclass(frozen=True)
class ImageRequest:
    """
    그림 한 장의 요청.

    prompt 는 그릴 것, negative 는 그리지 말 것(받는 provider 만 쓴다), seed 는 같은 그림을 다시 얻을 때의 씨앗이다
    (받는 provider 만 쓴다, 없으면 provider 가 고른다).
    """

    prompt: str
    references: tuple[ReferenceImage, ...] = ()
    negative: str = ''
    seed: int | None = None


@dataclass(frozen=True)
class GeneratedImage:
    """
    만든 그림과 그것을 만든 사정. 토큰 수는 공급자가 알려 주면 채운다(원가를 장마다 매기는 공급자는 비어 있다).
    seed 는 provider 가 쓴 씨앗이다(쓰지 않는 provider 면 None).
    """

    data: bytes
    mime_type: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    seed: int | None = None


class ImageProvider(Protocol):
    """
    그림을 만드는 것의 모양. 이 메서드와 세 이름이 있으면 image provider 다.

    kind 는 종류(gemini_image, comfyui, fake), model 은 모델의 이름이다. 호출과 원가를 기록할 때 쓴다.
    supports_references 가 아니면 참고 그림을 넘기지 않는다(넘기면 ProviderError(references_unsupported)).
    """

    kind: str
    model: str
    supports_references: bool

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        """그림 한 장을 만든다. 실패하면 ProviderError."""
        ...
