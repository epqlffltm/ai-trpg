# shared/ai-core/src/ai_core/gemini_image.py

"""
Gemini 의 그림 모델(Nano Banana)을 부르는 image provider(#983). generateContent 를 SDK 없이 httpx 로 부른다.

  - 주소: {base}/v1beta/models/{모델}:generateContent. 머리: x-goog-api-key(키를 주소에 싣지 않는다)
    글 모델(ai_core/gemini.py)과 같은 주소의 같은 판(v1beta)이다. 그림은 흘려 받지 않는다
  - 본문: contents 에 참고 그림(inlineData)과 지시 글. generationConfig 의 responseModalities 는 IMAGE 만,
    imageConfig 에 비율(aspectRatio)과 크기(imageSize: 1K, 2K, 4K)를 싣는다.
    대화를 저장하지 말라고 store 를 false 로 싣는다
  - 참고 그림: Nano Banana 2.1·2 는 한 요청에 인물 그림 4장, 물건 그림 10장까지다(공식 문서, 2026-11-04).
    넘으면 앞의 것만 보낸다(MAX_CHARACTER_REFERENCES, MAX_OBJECT_REFERENCES)
  - 답: candidates[0].content.parts 에서 생각(thought)이 아닌 inlineData 를 그림으로 읽는다.
    그림이 없으면 막힌 까닭(promptFeedback.blockReason, finishReason 이 STOP 이 아님)이 있으면 refused,
    없으면 no_image 다
  - 원가: 그림 토큰으로 매긴다(usageMetadata 의 promptTokenCount, candidatesTokenCount).
    만든 그림에는 SynthID 표식이 들어간다
"""

import base64
import binascii
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr

from ai_core.image_http import limited, post_json
from ai_core.image_provider import (
    MALFORMED,
    NO_IMAGE,
    REFUSED,
    GeneratedImage,
    ImageRequest,
    ReferenceImage,
    ReferenceKind,
)
from ai_core.provider import ProviderError

# 한 요청에 넘기는 참고 그림의 상한(Nano Banana 2.1·2 의 공식 상한)
MAX_CHARACTER_REFERENCES = 4
MAX_OBJECT_REFERENCES = 10
# 그림 없이 끝났어도 거절로 보지 않는 끝난 까닭
NOT_BLOCKED = frozenset({'STOP', 'MAX_TOKENS', 'FINISH_REASON_UNSPECIFIED'})


def generate_url(base_url: str, model: str) -> str:
    """그림을 만드는 주소. 설정한 주소의 끝에 / 가 있든 없든 같다."""
    return f'{base_url.rstrip("/")}/v1beta/models/{model}:generateContent'


def capped(references: tuple[ReferenceImage, ...]) -> list[ReferenceImage]:
    """보낼 참고 그림. 종류마다 상한까지 앞의 것만."""
    characters = [image for image in references if image.kind == ReferenceKind.CHARACTER][:MAX_CHARACTER_REFERENCES]
    objects = [image for image in references if image.kind == ReferenceKind.OBJECT][:MAX_OBJECT_REFERENCES]
    return [*characters, *objects]


def image_part(image: ReferenceImage) -> dict[str, Any]:
    """참고 그림 하나를 보내는 모양."""
    return {'inlineData': {'mimeType': image.mime_type, 'data': base64.b64encode(image.data).decode('ascii')}}


def request_body(request: ImageRequest, aspect_ratio: str, image_size: str) -> dict[str, Any]:
    """보낼 본문. 참고 그림이 앞, 지시 글이 뒤다."""
    parts = [*(image_part(image) for image in capped(request.references)), {'text': request.prompt}]
    return {
        'contents': [{'role': 'user', 'parts': parts}],
        'generationConfig': {
            'responseModalities': ['IMAGE'],
            'imageConfig': {'aspectRatio': aspect_ratio, 'imageSize': image_size},
        },
        'store': False,
    }


def first_candidate(answer: Any) -> dict[str, Any]:
    """첫 후보. 없으면 빈 것."""
    candidates = answer.get('candidates') if isinstance(answer, dict) else None
    return candidates[0] if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict) else {}


def image_data_of(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """후보에서 생각이 아닌 마지막 그림(inlineData). 없으면 None."""
    content = candidate.get('content')
    parts = content.get('parts') if isinstance(content, dict) else None
    found = None
    for part in parts if isinstance(parts, list) else []:
        data = part.get('inlineData') or part.get('inline_data') if isinstance(part, dict) else None
        if isinstance(data, dict) and not part.get('thought'):
            found = data
    return found


def decoded(data: dict[str, Any]) -> tuple[bytes, str]:
    """inlineData 의 바이트와 형식. 읽을 수 없으면 ProviderError(malformed)."""
    try:
        raw = base64.b64decode(str(data.get('data', '')), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProviderError(MALFORMED) from exc
    mime_type = data.get('mimeType') or data.get('mime_type') or 'image/png'
    return limited(raw), str(mime_type)


def was_blocked(answer: Any, candidate: dict[str, Any]) -> bool:
    """공급자가 막았는가. 지시가 막혔거나(blockReason), 후보가 STOP 이 아닌 까닭으로 끝났다."""
    feedback = answer.get('promptFeedback') if isinstance(answer, dict) else None
    if isinstance(feedback, dict) and feedback.get('blockReason'):
        return True
    reason = candidate.get('finishReason')
    return bool(reason) and reason not in NOT_BLOCKED


def token_count(answer: Any, name: str) -> int | None:
    """usageMetadata 의 토큰 수. 없으면 None."""
    usage = answer.get('usageMetadata') if isinstance(answer, dict) else None
    value = usage.get(name) if isinstance(usage, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def read_image(answer: Any, model: str) -> GeneratedImage:
    """답에서 그림을 읽는다. 그림이 없으면 막혔으면 refused, 아니면 no_image."""
    candidate = first_candidate(answer)
    data = image_data_of(candidate)
    if data is None:
        raise ProviderError(REFUSED if was_blocked(answer, candidate) else NO_IMAGE)
    raw, mime_type = decoded(data)
    return GeneratedImage(
        data=raw,
        mime_type=mime_type,
        model=model,
        input_tokens=token_count(answer, 'promptTokenCount'),
        output_tokens=token_count(answer, 'candidatesTokenCount'),
    )


@dataclass
class GeminiImageProvider:
    """
    Nano Banana 를 부르는 것. http 는 서버가 넘기는 클라이언트(span 이 걸린다), timeout 은 한 장의 상한(초)이다.
    aspect_ratio 는 1:1, 3:4 같은 비율, image_size 는 1K, 2K, 4K 다(값은 공급자가 검사한다).
    """

    @property
    def kind(self) -> str:
        """종류. 클래스마다 정해져 있다."""
        return 'gemini_image'

    @property
    def supports_references(self) -> bool:
        """참고 그림을 받는가. 클래스마다 정해져 있다."""
        return True

    http: httpx.AsyncClient
    base_url: str
    api_key: SecretStr
    model: str
    timeout: float = 120.0
    aspect_ratio: str = '1:1'
    image_size: str = '1K'

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        """그림 한 장을 만든다."""
        body = request_body(request, self.aspect_ratio, self.image_size)
        headers = {'x-goog-api-key': self.api_key.get_secret_value()}
        answer = await post_json(self.http, generate_url(self.base_url, self.model), body, headers, self.timeout)
        return read_image(answer, self.model)
