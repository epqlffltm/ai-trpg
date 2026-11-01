# story-server/scripts/try_scene.py

"""
실제 언어 모델로 story 의 장면을 써 보며 두 가지를 잰다. 서버도 DB 도 쓰지 않고, 여기 적어 둔 예시 판 하나로.

  - cast: 장면의 인물 수(엔진의 상한은 4명, app/engine/scene.py)가 모델마다 맞는가.
    인물 수를 바꿔 같은 장면을 쓰게 하고, 표식을 지켰는가(장면에 없는 인물의 줄, 표식 없는 줄),
    인물 가운데 몇이 말했는가, 답의 길이와 시간을 센다. 상한을 넘는 수(5, 6)도 견줘 볼 수 있게 엔진을 거치지 않는다.
  - flow: 이벤트가 열린 행동의 답(장면 지시를 받는다)과, 이어서 선택지를 고른 행동의 답(반응)을 차례로 쓰게 하고
    두 번의 입력·출력 토큰과 원가를 센다. 지금은 둘을 따로 청구한다. 묶을지 정할 근거다.

자동 테스트가 아니라서 CI 에서 돌지 않는다(값을 세는 함수는 tests/test_try_scene.py 가 본다).
서버가 쓰는 것과 같은 카드(app/turns/prompt.py)와 말 조각 나누기(app/turns/segments.py)를 그대로 거친다.

    uv run python -m scripts.try_scene --model gemma4:26b
    uv run python -m scripts.try_scene --model gemma4:26b qwen3.6:27b --check cast --cast 1 2 3 4 5 6 --repeat 3
    uv run python -m scripts.try_scene --model gemma4:26b --check flow --price-in 0.3 --price-out 1.2 --out scene.md

story-server 폴더에서 -m 으로 돌린다. 그래야 app 을 찾는다.
주소는 OpenAI 모양이면 된다(기본은 로컬 Ollama). API 키가 필요한 곳은 --api-key-env 로 키가 든 환경 변수의 이름을 준다.
모델마다 먼저 아주 짧은 요청을 보내 메모리에 올려 둔다(--no-warmup 으로 끈다). 한 모델이 실패해도 나머지는 돈다.
판단은 사람이 한다. --repeat 로 여러 번 돌린다. 한 번의 결과는 운일 수 있다.

예시는 공개 저장소에 올라가도 되는 지어낸 설정이다(바닷가 마을의 여름 축제).
"""

import argparse
import asyncio
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import httpx
from ai_core.openai_compat import OpenAICompatProvider
from ai_core.provider import ChatMessage, Completion, GenerationParams, ProviderError, Role
from conversation_core.window import Turn
from pydantic import SecretStr

from app.engine.clock import MINUTES_PER_HOUR
from app.engine.state import StoryState
from app.engine.world import World, read_world
from app.turns.briefing import Briefing, read_briefing
from app.turns.prompt import build_messages, render_card, scene_card
from app.turns.segments import Segment, render_segments, speaker_labels, split_segments

# 서버의 기본값과 같다(app/core/config.py 의 story_output_limit, story_temperature)
PARAMS = GenerationParams(max_tokens=1024, temperature=0.9)
WARMUP_MESSAGES = [ChatMessage(role=Role.USER, content='안녕')]
WARMUP_PARAMS = GenerationParams(max_tokens=8, temperature=0.0)

# 예시 판의 인물 여섯. 앞에서부터 장면에 넣는다
PEOPLE = (
    ('mina', '미나', '등대지기의 딸. 말이 빠르고 호기심이 많다.', '어? 그거 뭐야? 나도 보여 줘!'),
    ('jun', '준', '어선을 모는 청년. 무뚝뚝하지만 정이 많다.', '...배 시간 늦겠다. 빨리 와.'),
    ('sora', '소라', '빙수 가게 주인. 늘 웃으며 남의 사정을 다 안다.', '어머, 오늘도 왔네? 단골 대접해 줄게.'),
    ('hana', '하나', '마을 축제의 사회자. 목소리가 크고 성격이 급하다.', '자자, 다들 모이세요! 시간 없어요!'),
    ('teo', '테오', '여름마다 오는 화가. 느릿느릿 말한다.', '음... 이 빛은... 지금만 볼 수 있지.'),
    ('rin', '린', '등대 고양이를 돌보는 아이. 수줍음이 많다.', '저, 저기... 고양이 못 봤어요?'),
)
FESTIVAL_SCENE = '광장에 등불이 켜지고 축제가 시작된다. 사회자가 사용자를 무대로 부른다.'
CHOICES = ('무대에 올라간다', '못 들은 척한다')
ARRIVAL = '광장으로 갔다. 지금은 1일째 저녁.'


def world_document() -> dict:
    """예시 판의 문서. 엔진(World)과 카드(Briefing)가 함께 읽는 모양이다."""
    return {
        'name': '바닷가 마을의 여름',
        'intro_html': '<p>작은 바닷가 마을. 오늘 밤은 일 년에 한 번 있는 등불 축제다.</p>',
        'slots': [{'id': 'day', 'name': '낮', 'start_hour': 9}, {'id': 'evening', 'name': '저녁', 'start_hour': 18}],
        'start_slot': 'evening',
        'start_place': 'square',
        'places': [{'id': 'square', 'name': '광장', 'description': '등불이 줄지어 걸린 바닷가 광장.'}],
        'items': [],
        'cast': [
            {
                'id': cast_id,
                'character': {'name': name, 'intro_html': f'<p>{intro}</p>', 'speech_examples': speech},
                'affection': {'start': 30, 'stages': [{'name': '아는 사이', 'at': 0}, {'name': '친구', 'at': 30}]},
            }
            for cast_id, name, intro, speech in PEOPLE
        ],
    }


@dataclass(frozen=True)
class Sample:
    """예시 판을 엔진과 카드가 읽은 것."""

    world: World
    briefing: Briefing


def sample() -> Sample:
    document = world_document()
    return Sample(world=read_world(document), briefing=read_briefing(document))


def evening_state(world: World) -> StoryState:
    """1일째 저녁의 광장."""
    evening = next(slot for slot in world.slots if slot.id == 'evening')
    return StoryState(minutes=evening.start_hour * MINUTES_PER_HOUR, place='square')


def cast_of(size: int) -> tuple[str, ...]:
    """장면의 인물 size 명(앞에서부터). 상한 4명을 넘는 수도 그대로 준다."""
    return tuple(cast_id for cast_id, *_ in PEOPLE[:size])


def scene_messages(source: Sample, cast: Sequence[str], event: str, window: list[Turn]) -> list[ChatMessage]:
    """서버와 같은 카드와 최근의 말로 만든 메시지."""
    state = evening_state(source.world)
    card = render_card(source.briefing, scene_card(source.briefing, source.world, state, cast, event))
    return build_messages(card, window)


def labels_of(source: Sample, cast: Sequence[str]) -> dict[str, str]:
    """장면의 인물의 표식 이름 → id."""
    return speaker_labels((cast_id, source.briefing.cast_name(cast_id)) for cast_id in cast)


@dataclass(frozen=True)
class CastStats:
    """
    답 하나를 장면의 인물로 센 것. lines 는 조각의 수, narration 은 서술의 수,
    spoke 는 말한 인물(장면의 차례), silent 는 한 줄도 없는 인물, dropped 는 장면에 없는 인물의 줄(버렸다)이다.
    """

    lines: int
    narration: int
    spoke: tuple[str, ...]
    silent: tuple[str, ...]
    dropped: int


def cast_stats(segments: Sequence[Segment], dropped: int, cast: Sequence[str]) -> CastStats:
    """조각들과 버린 줄의 수를 장면의 인물로 센다."""
    speakers = {segment.speaker for segment in segments}
    return CastStats(
        lines=len(segments),
        narration=sum(1 for segment in segments if segment.speaker is None),
        spoke=tuple(cast_id for cast_id in cast if cast_id in speakers),
        silent=tuple(cast_id for cast_id in cast if cast_id not in speakers),
        dropped=dropped,
    )


def cost_of(completion: Completion | None, price_in: Decimal | None, price_out: Decimal | None) -> Decimal | None:
    """한 번의 원가(USD). 토큰 수나 단가(백만 토큰당)가 없으면 None."""
    if completion is None or price_in is None or price_out is None:
        return None
    if completion.input_tokens is None or completion.output_tokens is None:
        return None
    million = Decimal(1_000_000)
    return (completion.input_tokens * price_in + completion.output_tokens * price_out) / million


@dataclass
class Call:
    """모델을 한 번 부른 것. 실패하면 problem 에 적는다."""

    seconds: float
    completion: Completion | None = None
    problem: str | None = None

    @property
    def text(self) -> str:
        return self.completion.text if self.completion is not None else ''


async def call(provider, messages: list[ChatMessage]) -> Call:
    """한 번 부른다. 실패해도 예외를 올리지 않고 적는다."""
    started = time.perf_counter()
    try:
        completion = await provider.complete(messages, PARAMS)
    except ProviderError as error:
        return Call(time.perf_counter() - started, problem=f'provider 실패: {error}')
    return Call(time.perf_counter() - started, completion=completion)


@dataclass
class CastTrial:
    """장면의 인물 수 하나로 한 번 쓴 것."""

    model: str
    size: int
    call: Call
    stats: CastStats | None = None


async def run_cast_trial(provider, source: Sample, size: int) -> CastTrial:
    """인물 size 명의 장면에서 이벤트의 장면을 쓰게 하고 센다."""
    cast = cast_of(size)
    messages = scene_messages(source, cast, FESTIVAL_SCENE, [Turn(role='action', content=ARRIVAL)])
    done = await call(provider, messages)
    if done.completion is None:
        return CastTrial(provider.model, size, done)
    segments, dropped = split_segments(done.text, labels_of(source, cast))
    return CastTrial(provider.model, size, done, cast_stats(segments, dropped, cast))


@dataclass
class FlowTrial:
    """이벤트의 장면(첫 답)과 선택지의 반응(둘째 답)을 차례로 쓴 것."""

    model: str
    scene: Call
    reaction: Call | None = None
    costs: tuple[Decimal | None, Decimal | None] = (None, None)


async def run_flow_trial(provider, source: Sample, price_in: Decimal | None, price_out: Decimal | None) -> FlowTrial:
    """
    이벤트가 열린 행동에 답하고, 그 답을 지난 말로 둔 채 선택지를 고른 행동에 답한다(서버의 두 번의 청구와 같다).
    첫 답이 실패하면 둘째는 부르지 않는다.
    """
    cast = cast_of(4)
    direction = f'{FESTIVAL_SCENE}\n고를 수 있는 것: {" / ".join(CHOICES)}'
    first = await call(provider, scene_messages(source, cast, direction, [Turn(role='action', content=ARRIVAL)]))
    if first.completion is None:
        return FlowTrial(provider.model, first)
    segments, _ = split_segments(first.text, labels_of(source, cast))
    window = [
        Turn(role='action', content=ARRIVAL),
        Turn(role='assistant', content=render_segments(segments)),
        Turn(role='action', content=f'고른 것: {CHOICES[0]}'),
    ]
    second = await call(provider, scene_messages(source, cast, '', window))
    costs = (cost_of(first.completion, price_in, price_out), cost_of(second.completion, price_in, price_out))
    return FlowTrial(provider.model, first, second, costs)


def count_or_dash(value: int | None) -> str:
    return str(value) if value is not None else '-'


def tokens(call_: Call | None) -> str:
    """'입력/출력' 토큰. 모르면 '-'."""
    if call_ is None or call_.completion is None:
        return '-'
    return f'{count_or_dash(call_.completion.input_tokens)}/{count_or_dash(call_.completion.output_tokens)}'


def output_ratio(first: Call, second: Call | None) -> str:
    """둘째 답의 출력 토큰 / 첫째 답의 출력 토큰. 모르면 '-'."""
    if second is None or first.completion is None or second.completion is None:
        return '-'
    before, after = first.completion.output_tokens, second.completion.output_tokens
    return f'{after / before:.2f}' if before and after is not None else '-'


def money(value: Decimal | None) -> str:
    return f'${value:.5f}' if value is not None else '-'


def cast_line(trial: CastTrial) -> str:
    """표의 한 줄."""
    head = f'| {trial.model} | {trial.size} | {trial.call.seconds:.1f}s | {tokens(trial.call)} |'
    if trial.stats is None:
        return f'{head} {trial.call.problem} | | | |'
    stats = trial.stats
    silent = ', '.join(stats.silent) or '-'
    return (
        f'{head} {len(stats.spoke)}/{trial.size} | {silent} | {stats.dropped} | {stats.lines}(서술 {stats.narration}) |'
    )


def flow_line(trial: FlowTrial) -> str:
    """표의 한 줄. 둘째/첫째는 출력 토큰의 비율이다."""
    first, second = trial.scene, trial.reaction
    problem = first.problem or (second.problem if second is not None else None) or ''
    ratio = output_ratio(first, second)
    total = None if None in trial.costs else sum(cost for cost in trial.costs if cost is not None)
    return (
        f'| {trial.model} | {tokens(first)} | {tokens(second)} | {ratio} | '
        f'{money(trial.costs[0])} | {money(trial.costs[1])} | {money(total)} | {problem} |'
    )


CAST_HEAD = (
    '| 모델 | 인물 | 시간 | 토큰(입/출) | 말한 인물 | 말 없는 인물 | 버린 줄 | 조각 |\n'
    '| --- | --- | --- | --- | --- | --- | --- | --- |'
)
FLOW_HEAD = (
    '| 모델 | 장면(입/출) | 반응(입/출) | 반응/장면 출력 | 장면 원가 | 반응 원가 | 합 | 문제 |\n'
    '| --- | --- | --- | --- | --- | --- | --- | --- |'
)


@dataclass
class Report:
    """돌린 것 전부."""

    casts: list[CastTrial] = field(default_factory=list)
    flows: list[FlowTrial] = field(default_factory=list)

    def tables(self) -> str:
        parts = []
        if self.casts:
            parts += ['## 장면의 인물 수', CAST_HEAD, *(cast_line(trial) for trial in self.casts)]
        if self.flows:
            parts += ['', '## 이벤트의 장면과 선택지의 반응', FLOW_HEAD, *(flow_line(trial) for trial in self.flows)]
        return '\n'.join(parts)

    def texts(self) -> str:
        """쓴 글 전부. 사람이 읽고 판단한다."""
        lines = [f'### {trial.model}, 인물 {trial.size}\n\n{trial.call.text}\n' for trial in self.casts]
        for trial in self.flows:
            reaction = trial.reaction.text if trial.reaction is not None else ''
            lines.append(f'### {trial.model}, 장면\n\n{trial.scene.text}\n\n### {trial.model}, 반응\n\n{reaction}\n')
        return '\n'.join(lines)


def read_arguments() -> argparse.Namespace:
    """명령줄의 값을 읽는다."""
    parser = argparse.ArgumentParser(description='실제 언어 모델로 story 의 장면을 써 보며 잰다.')
    parser.add_argument('--model', required=True, nargs='+', help='모델 이름. 여럿을 띄어 적는다')
    parser.add_argument('--check', nargs='+', default=['cast', 'flow'], choices=['cast', 'flow'], help='잴 것')
    parser.add_argument('--cast', nargs='+', type=int, default=[1, 2, 3, 4, 5], help='장면의 인물 수(1~6)')
    parser.add_argument('--repeat', type=int, default=1, help='같은 것을 몇 번 돌릴까')
    parser.add_argument('--price-in', type=Decimal, help='입력 단가(USD, 백만 토큰당). 주면 원가를 센다')
    parser.add_argument('--price-out', type=Decimal, help='출력 단가(USD, 백만 토큰당)')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1', help='OpenAI 모양의 주소')
    parser.add_argument('--api-key-env', help='API 키가 든 환경 변수의 이름(키를 명령줄에 적지 않는다)')
    parser.add_argument('--timeout', type=float, default=300.0, help='한 요청을 기다리는 시간(초)')
    parser.add_argument('--no-warmup', action='store_true', help='모델을 미리 올리지 않는다')
    parser.add_argument('--out', type=Path, help='표와 글을 남길 파일(UTF-8)')
    arguments = parser.parse_args()
    if any(size < 1 or size > len(PEOPLE) for size in arguments.cast):
        parser.error(f'--cast 는 1~{len(PEOPLE)} 사이다')
    return arguments


def make_provider(client: httpx.AsyncClient, arguments: argparse.Namespace, model: str) -> OpenAICompatProvider:
    """명령줄의 값으로 provider 를 만든다. 키는 환경 변수에서 읽는다."""
    api_key = os.environ.get(arguments.api_key_env, '') if arguments.api_key_env else ''
    return OpenAICompatProvider(
        client=client,
        base_url=arguments.base_url,
        model=model,
        timeout=arguments.timeout,
        api_key=SecretStr(api_key) if api_key else None,
    )


async def warm_up(provider: OpenAICompatProvider) -> None:
    """모델을 메모리에 올려 둔다. 실패해도 넘어간다."""
    try:
        await provider.complete(WARMUP_MESSAGES, WARMUP_PARAMS)
    except ProviderError:
        return


async def run_model(provider, source: Sample, arguments: argparse.Namespace, report: Report) -> None:
    """모델 하나로 고른 것을 --repeat 번씩 잰다. 하나씩 끝나는 대로 찍는다."""
    for _ in range(arguments.repeat):
        if 'cast' in arguments.check:
            for size in arguments.cast:
                trial = await run_cast_trial(provider, source, size)
                print(cast_line(trial), flush=True)
                report.casts.append(trial)
        if 'flow' in arguments.check:
            flow = await run_flow_trial(provider, source, arguments.price_in, arguments.price_out)
            print(flow_line(flow), flush=True)
            report.flows.append(flow)


async def run_all(arguments: argparse.Namespace) -> Report:
    """모델마다 잰다."""
    report = Report()
    source = sample()
    async with httpx.AsyncClient() as client:
        for model in arguments.model:
            provider = make_provider(client, arguments, model)
            if not arguments.no_warmup:
                await warm_up(provider)
            await run_model(provider, source, arguments, report)
    return report


def main() -> None:
    """명령줄을 읽고, 돌리고, 표를 찍고, 원하면 파일로 남긴다."""
    arguments = read_arguments()
    report = asyncio.run(run_all(arguments))
    print()
    print(report.tables())
    if arguments.out is not None:
        arguments.out.write_text(f'{report.tables()}\n\n## 쓴 글\n\n{report.texts()}', encoding='utf-8')
        print(f'\n저장했다: {arguments.out}')


if __name__ == '__main__':
    main()
