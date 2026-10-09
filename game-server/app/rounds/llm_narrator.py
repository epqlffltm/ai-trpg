# game-server/app/rounds/llm_narrator.py

"""
언어 모델로 GM 의 서술을 쓰는 서술자. app/rounds/narrator.py 의 Narrator 모양을 따른다.

하는 일은 셋이다. 셋을 한 함수에 섞지 않는다.
  1. 메시지를 조립한다(app/rounds/prompt.py, 순수 함수).
  2. provider 를 부른다(app/ai/provider.py). 어느 모델인지는 모른다.
  3. 받은 글을 검사한다. 장면으로 쓸 수 있는 글만 돌려준다.

모델의 글은 장면이 될 뿐이다. 상태를 바꾸지 않는다. 결과(판정, HP, 죽음)는 엔진이 이미 정해 DB 에 적었다.
그래서 검사는 "장면으로 쓸 수 있는가"만 본다. 비어 있지 않고, 너무 길지 않은가.

실패하면 예외를 그대로 올린다. 라운드는 닫는 중에 머물고, 방장이 닫기를 다시 눌러 맡긴다(app/rounds/closing.py).
다시 시도하기와 다른 모델로 넘어가기는 다음 단계(⑤)에서 더한다.
"""

from dataclasses import dataclass

from app.ai.provider import GenerationParams, LLMProvider
from app.rounds.narrator import NarrationRequest
from app.rounds.prompt import build_messages

# 서술을 만들 때의 설정. 몇 문단의 장면이면 충분하다. 너무 딱딱하지 않게 조금 다양하게 쓴다
NARRATION_PARAMS = GenerationParams(max_tokens=800, temperature=0.8)

# 장면으로 받는 글의 상한(글자 수). 다음 라운드의 요청에 다시 들어가므로, 길면 그만큼 다음 호출이 비싸진다
SCENE_MAX_LENGTH = 4000


class NarrationError(Exception):
    """서술자가 장면으로 쓸 글을 만들지 못했다. 글이 비었거나, 너무 길거나, 요청에 이야기의 바탕이 없다."""


def accept_scene(text: str) -> str:
    """
    모델의 글을 장면으로 받아도 되는지 보고, 앞뒤 공백을 뗀 글을 돌려준다. 안 되면 NarrationError.

    길이를 넘는 글을 잘라서 받지 않는다. 문장 중간에서 끊긴 장면이 기록으로 굳는다.
    """
    scene = text.strip()
    if not scene:
        raise NarrationError('empty')
    if len(scene) > SCENE_MAX_LENGTH:
        raise NarrationError('too_long')
    return scene


@dataclass(frozen=True)
class LLMNarrator:
    """언어 모델로 서술하는 서술자. provider 를 바꿔 끼우면 다른 모델이 쓴다."""

    provider: LLMProvider
    params: GenerationParams = NARRATION_PARAMS

    async def narrate(self, request: NarrationRequest) -> str:
        """닫힌 라운드의 결과를 서술한다. 돌려준 글이 다음 라운드의 장면이 된다."""
        if request.story is None:
            raise NarrationError('no_story')
        completion = await self.provider.complete(build_messages(request), self.params)
        return accept_scene(completion.text)
