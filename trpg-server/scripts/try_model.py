# trpg-server/scripts/try_model.py

"""
모델 하나를 실제로 불러 본다. 짧은 장면 하나를 쓰게 하고, 글과 토큰 수, 원가, 걸린 시간을 찍는다.

쓰는 때.
  - 모델 목록에 넣은 모델(scripts/models.py add)이 API 모델 이름과 키로 정말 불리는지 볼 때. 켜기 전이다.
  - 날짜판을 바꾼 뒤(switch-snapshot) 다시 불리는지 볼 때.
  - 키를 새로 넣었거나 바꾼 뒤.
  - 글자당 토큰 수를 잴 때. 서술의 입력 예산은 글자 수로 어림한다(app/rounds/budget.py).
    --text-file 로 긴 한국어 글을 보내면 보낸 글자 수와 받은 입력 토큰 수의 비율을 찍는다.
    짧은 예시 장면은 역할의 머리 같은 고정 토큰이 커서 비율이 부풀어 보인다.

    uv run python -m scripts.try_model gpt-6-luna
    uv run python -m scripts.try_model gpt-6-luna --reasoning low --max-tokens 400
    uv run python -m scripts.try_model gemma4:26b
    uv run python -m scripts.try_model gpt-6-luna --text-file ../long.txt

trpg-server 폴더에서 -m 으로 돌린다. 설정(.env)의 DB, 키(OPENAI_API_KEY), 서버 곁의 모델의 주소를 쓴다.
서버와 같은 것(app/ai/routing.py)으로 창구를 고른다. 이름표면 모델 목록대로, 아니면 서버 곁의 모델이다.
꺼진 모델도 부른다. 켜기 전에 불러 보려는 것이다. 은퇴한 모델은 부르지 않는다.

실제로 부르므로 값이 든다(장면 하나, 몇 원). 서술의 품질을 보는 것은 scripts/try_narration.py 와 평가 장면(evals/)이다.
키는 찍지 않는다. 실패하면 까닭(status_401, timeout …)만 찍는다. 응답의 본문은 찍지 않는다.
예시 장면은 공개 저장소에 올라가도 되는 개그 설정이다. --text-file 의 글은 저장소에 두지 않는다.
"""

import argparse
import asyncio
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.ai.calls import chars_of
from app.ai.costs import PriceTag, cost_usd
from app.ai.provider import ChatMessage, Completion, GenerationParams, ProviderError, Reasoning, Role
from app.ai.routing import ModelRouter
from app.core.config import get_settings
from app.core.database import create_engine, create_session_factory
from app.rounds.narrator_setup import build_router

MESSAGES = [
    ChatMessage(Role.SYSTEM, '너는 TRPG 의 GM 이다. 한국어로 두세 문장의 장면을 쓴다. 숫자와 규칙은 말하지 않는다.'),
    ChatMessage(Role.USER, '엘프 폭주족이 열일곱 행성을 잇는 고속도로를 달린다. 뒤에서 사이렌이 울린다.'),
]
# 따로 적지 않았을 때의 출력 상한(토큰). 두세 문장이면 충분하다
DEFAULT_MAX_TOKENS = 300
TEMPERATURE = 0.8


def build_parser() -> argparse.ArgumentParser:
    """명령줄의 모양."""
    parser = argparse.ArgumentParser(description='모델 하나를 실제로 불러 본다.')
    parser.add_argument('model', help='모델 목록의 이름표(gpt-6-luna) 또는 서버 곁의 모델의 이름(gemma4:26b)')
    parser.add_argument('--reasoning', choices=list(Reasoning), default=Reasoning.NONE, help='생각의 깊이')
    parser.add_argument('--max-tokens', type=int, default=DEFAULT_MAX_TOKENS, help='출력 상한(토큰)')
    parser.add_argument(
        '--text-file', type=Path, help='이 파일(UTF-8)의 글을 사람의 말로 보낸다. 글자당 토큰 수를 잴 때'
    )
    return parser


def params_of(args: argparse.Namespace) -> GenerationParams:
    """명령줄의 값으로 생성 설정을 만든다."""
    return GenerationParams(max_tokens=args.max_tokens, temperature=TEMPERATURE, reasoning=Reasoning(args.reasoning))


def messages_of(text: str | None) -> list[ChatMessage]:
    """보낼 메시지. 글이 없으면 예시 장면, 있으면 예시의 시스템 지시 뒤에 그 글을 사람의 말로."""
    if text is None:
        return MESSAGES
    return [MESSAGES[0], ChatMessage(Role.USER, text)]


def read_text(path: Path | None) -> str | None:
    """--text-file 의 글. 적지 않았으면 None."""
    return None if path is None else path.read_text(encoding='utf-8')


@dataclass
class FirstText:
    """첫 글이 언제 왔는지 적어 두는 것. 앉은 사람이 기다리는 시간이다."""

    started: float
    at: float | None = None

    def mark(self) -> None:
        """처음 한 번만 적는다."""
        if self.at is None:
            self.at = time.perf_counter()

    def ms(self) -> int | None:
        """부르기 시작해서 첫 글이 오기까지(밀리초). 글이 오지 않았으면 None."""
        return None if self.at is None else round((self.at - self.started) * 1000)


def known(value: int | None) -> str:
    """토큰 수. 모르면 '모름'."""
    return '모름' if value is None else str(value)


def cost_line(completion: Completion, price: PriceTag | None) -> str:
    """원가의 줄. 모델 목록에 없는 모델이면 세지 않는다."""
    if price is None:
        return '원가: 모델 목록에 없는 모델이라 세지 않는다'
    if price.cost is None:
        return '원가: 오늘의 단가가 없다(scripts.models set-cost)'
    amount = cost_usd(completion, price.cost)
    return '원가: 토큰 수를 몰라 세지 못했다' if amount is None else f'원가: ${amount}'


def ratio_line(chars: int, completion: Completion) -> str:
    """보낸 글자 수와 글자당 입력 토큰 수의 줄. 입력 토큰 수를 모르면 글자 수만."""
    if completion.input_tokens is None or chars == 0:
        return f'보낸 글자: {chars}자 (글자당 토큰 모름)'
    return f'보낸 글자: {chars}자, 글자당 입력 토큰 {completion.input_tokens / chars:.2f}'


def summary_lines(
    kind: str, completion: Completion, price: PriceTag | None, total_ms: int, first_ms: int | None, chars: int
) -> list[str]:
    """부른 결과의 요약. 글은 흘려 받을 때 이미 찍었다."""
    return [
        f'창구 {kind}, 답한 모델 {completion.model}, 멈춘 이유 {completion.finish_reason or "모름"}'
        + (' (길이 상한에 걸림)' if completion.truncated else ''),
        f'토큰: 입력 {known(completion.input_tokens)}(캐시 {known(completion.cached_input_tokens)}), '
        f'출력 {known(completion.output_tokens)}(생각 {known(completion.reasoning_tokens)})',
        cost_line(completion, price),
        f'시간: 첫 글 {first_ms if first_ms is not None else "-"}ms, 전체 {total_ms}ms',
        ratio_line(chars, completion),
    ]


async def try_once(
    router: ModelRouter,
    name: str,
    params: GenerationParams,
    write: Callable[[str], None],
    messages: list[ChatMessage] = MESSAGES,
) -> tuple[int, list[str]]:
    """
    한 번 불러 본다. 흘려 받는 글은 오는 대로 write 에 넘긴다. 끝낼 번호(0 잘 됨, 1 실패)와 찍을 줄들을 돌려준다.

    꺼진 모델도 부른다(allow_disabled). 고르지 못하거나 부르다 실패하면 까닭만 돌려준다.
    """
    try:
        route = await router.route(name, allow_disabled=True)
    except ProviderError as error:
        return 1, [f'{name}: 부를 수 없다 ({error})']
    first = FirstText(started=time.perf_counter())

    def on_text(piece: str) -> None:
        first.mark()
        write(piece)

    try:
        completion = await route.provider.complete(messages, params, on_text)
    except ProviderError as error:
        return 1, [f'{name}: 부르다 실패했다 ({error})']
    total_ms = round((time.perf_counter() - first.started) * 1000)
    summary = summary_lines(route.provider.kind, completion, route.price, total_ms, first.ms(), chars_of(messages))
    return 0, ['', *summary]


def write_live(piece: str) -> None:
    """흘려 받는 글을 오는 대로 찍는다."""
    print(piece, end='', flush=True)


async def run(args: argparse.Namespace) -> int:
    """설정의 DB 와 창구로 한 번 불러 보고 결과를 찍는다. 끝낼 번호를 돌려준다."""
    messages = messages_of(read_text(args.text_file))
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with httpx.AsyncClient() as client:
            router = build_router(settings, client, create_session_factory(engine))
            code, lines = await try_once(router, args.model.strip(), params_of(args), write_live, messages)
    finally:
        await engine.dispose()
    print('\n'.join(lines), file=sys.stderr if code else sys.stdout)
    return code


def main() -> None:
    """명령줄을 읽고 돌린다."""
    sys.exit(asyncio.run(run(build_parser().parse_args())))


if __name__ == '__main__':
    main()
