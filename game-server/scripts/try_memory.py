# game-server/scripts/try_memory.py

"""
지난 일과 인물의 이력을 넣고 뺀 서술을 실제 언어 모델로 견준다(#107 ③). 서버도 DB 도 쓰지 않는다.

평가 데이터(evals/memory/chase_log.yaml)의 20 라운드짜리 게임에 이어 21 라운드를 서술하게 한다
(evals/memory/narration.py).
지난 기록은 서버와 같이 최근 3 라운드다. 그 앞의 일을 넣지 않은 것(off)과 서버의 규칙으로 고른 것(on)을 견준다.
배신한 NPC 를 다시 만나는 장면(betrayal)과 도와준 NPC 를 다시 만나는 장면(helper)이 있다.

    uv run python -m scripts.try_memory --model gemma4:26b-a4b-it-qat --repeat 10 --out $HOME\\memory-narration.md
    uv run python -m scripts.try_memory --model gemma4:26b-a4b-it-qat --case betrayal --memory off on --style web_novel

장면마다 지난 일에만 있는 낱말(배신, 무전기, 주걱 …)이 나왔는지, 따옴표 속 말이 있는지를 센다.
끝에 같은 장면, 같은 방식으로 돌린 것끼리 묶어 센 표를 찍는다. 태도(차갑게, 반갑게)는 사람이 장면을 읽고 판단한다.
서술의 조립, provider, 장면 검사는 서버와 같다. 지난 일을 고르는 임베딩 모델은 --embedding-model 이다(같은 주소).
"""

import argparse
import asyncio
import time
from dataclasses import dataclass, replace
from pathlib import Path

import httpx

from app.ai.openai_compat import OpenAICompatProvider
from app.ai.openai_embedder import OpenAICompatEmbedder
from app.ai.provider import Completion, ProviderError
from app.assets.models import NarrationStyle
from app.core.config import get_settings
from app.memory.retrieval import MemoryThresholds
from app.rounds.llm_narrator import NARRATION_PARAMS, NarrationError, accept_completion
from app.rounds.narrator import NarrationRequest
from app.rounds.prompt import build_messages
from evals.memory.dataset import load_dataset
from evals.memory.narration import (
    CASES,
    MemoryCase,
    MemoryContext,
    MemoryMode,
    case_request,
    describe_contexts,
    memory_context,
    recall_hits,
    request_for,
)
from scripts.try_narration import QUOTE, Watch, is_sound, make_provider, seconds_or_dash, warm_up


@dataclass(frozen=True)
class MemoryTrial:
    """장면 하나를 한 방식으로 서술해 본 결과. recalled 는 장면에 나온 지난 일의 낱말, speech 는 따옴표 속 말의 수다."""

    model: str
    case: str
    mode: MemoryMode
    style: NarrationStyle
    seconds: float
    first_text: float | None = None
    completion: Completion | None = None
    scene: str | None = None
    problem: str | None = None
    recalled: tuple[str, ...] = ()
    speech: int = 0


def read_arguments() -> argparse.Namespace:
    """명령줄의 값을 읽는다."""
    parser = argparse.ArgumentParser(description='지난 일과 인물의 이력을 넣고 뺀 서술을 견준다.')
    parser.add_argument('--model', required=True, nargs='+', help='서술 모델. 여럿을 띄어 적는다')
    parser.add_argument('--case', nargs='+', default=list(CASES), choices=list(CASES))
    parser.add_argument('--memory', nargs='+', default=['off', 'on'], choices=[mode.value for mode in MemoryMode])
    parser.add_argument('--style', nargs='+', default=['classic'], choices=[style.value for style in NarrationStyle])
    parser.add_argument('--embedding-model', default='bge-m3', help='지난 일을 고를 임베딩 모델')
    parser.add_argument('--repeat', type=int, default=1, help='같은 장면, 방식, 문체로 몇 번 돌릴까')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1', help='OpenAI 모양의 주소')
    parser.add_argument('--timeout', type=float, default=300.0, help='한 요청을 기다리는 시간(초)')
    parser.add_argument('--no-reasoning-field', action='store_true', help='추론 수준을 보내지 않는다')
    parser.add_argument('--no-warmup', action='store_true', help='모델을 미리 올리지 않는다')
    parser.add_argument('--live', action='store_true', help='흘려 받는 글을 오는 대로 찍는다')
    parser.add_argument('--out', type=Path, help='표와 장면을 남길 파일(UTF-8)')
    return parser.parse_args()


def speech_count(scene: str) -> int:
    """따옴표 속 말의 수. 짧은 소리는 세지 않는다(try_narration 과 같다). 누가 말했는지는 사람이 본다."""
    return sum(1 for body in QUOTE.findall(scene) if not is_sound(body))


async def run_trial(
    provider: OpenAICompatProvider,
    case: MemoryCase,
    request: NarrationRequest,
    mode: MemoryMode,
    context: MemoryContext,
    style: NarrationStyle,
    live: bool = False,
) -> MemoryTrial:
    """장면 하나를 한 번 서술하게 한다. 실패해도 예외를 올리지 않고 결과에 적는다."""
    base = replace(request, style=style)
    messages = build_messages(request_for(mode, base, context))
    watch = Watch(started=time.perf_counter(), live=live)
    head = {'model': provider.model, 'case': case.name, 'mode': mode, 'style': style}
    try:
        completion = await provider.complete(messages, NARRATION_PARAMS, watch)
    except ProviderError as error:
        seconds = time.perf_counter() - watch.started
        return MemoryTrial(**head, seconds=seconds, first_text=watch.first, problem=f'provider 실패: {error}')
    seconds = time.perf_counter() - watch.started
    timing = {'seconds': seconds, 'first_text': watch.first, 'completion': completion}
    try:
        scene = accept_completion(completion)
    except NarrationError as error:
        return MemoryTrial(**head, **timing, problem=f'장면으로 받지 않음: {error}')
    recalled = tuple(recall_hits(scene, case, base))
    return MemoryTrial(**head, **timing, scene=scene, recalled=recalled, speech=speech_count(scene))


def describe(trial: MemoryTrial) -> str:
    """결과 하나를 읽기 좋은 글로."""
    head = f'## {trial.model} / {trial.case} / 지난 일 {trial.mode.value} / 문체 {trial.style.value}'
    lines = [f'{head} / {trial.seconds:.1f}초 (첫 글 {seconds_or_dash(trial.first_text)}초)']
    if trial.completion is not None:
        lines.append(f'토큰: 입력 {trial.completion.input_tokens}, 출력 {trial.completion.output_tokens}')
    if trial.problem is not None:
        lines.append(trial.problem)
    if trial.scene is not None:
        lines.append(f'장면 {len(trial.scene)}자 / 지난 일의 낱말 {list(trial.recalled)} / 따옴표 속 말 {trial.speech}')
        lines.extend(['', trial.scene])
    lines.append('')
    return '\n'.join(lines)


def average(values: list[int]) -> str:
    """평균을 소수 한 자리로. 값이 없으면 '-'."""
    return f'{sum(values) / len(values):.1f}' if values else '-'


def tally_row(group: list[MemoryTrial]) -> str:
    """같은 장면, 방식, 문체로 돌린 결과들을 센 한 줄."""
    first = group[0]
    scenes = [trial for trial in group if trial.scene is not None]
    tokens = [trial.completion.input_tokens for trial in scenes if trial.completion and trial.completion.input_tokens]
    cells = [
        first.model,
        first.case,
        first.mode.value,
        first.style.value,
        str(len(group)),
        str(len(group) - len(scenes)),
        f'{sum(1 for trial in scenes if trial.recalled)}/{len(scenes)}',
        average([len(trial.recalled) for trial in scenes]),
        f'{sum(1 for trial in scenes if trial.speech)}/{len(scenes)}',
        average(tokens),
    ]
    return '| ' + ' | '.join(cells) + ' |'


def tally(trials: list[MemoryTrial]) -> str:
    """같은 모델, 장면, 방식, 문체로 돌린 것끼리 묶어 센 표(마크다운). 돌린 차례대로."""
    groups: dict[tuple, list[MemoryTrial]] = {}
    for trial in trials:
        groups.setdefault((trial.model, trial.case, trial.mode, trial.style), []).append(trial)
    header = ['모델', '장면', '지난 일', '문체', '횟수', '실패', '떠올림', '낱말 수', '따옴표 속 말', '입력 토큰']
    rows = ['| ' + ' | '.join(header) + ' |', '| ' + ' | '.join('---' for _ in header) + ' |']
    rows.extend(tally_row(group) for group in groups.values())
    return '\n'.join(rows)


def current_thresholds() -> MemoryThresholds:
    """서버의 기준. 설정의 값이다."""
    settings = get_settings()
    return MemoryThresholds(settings.memory_max_distance, settings.memory_keyword_max_distance)


async def prepare(
    client: httpx.AsyncClient, arguments: argparse.Namespace
) -> list[tuple[MemoryCase, NarrationRequest, MemoryContext]]:
    """장면마다 요청과, on 에서 넣을 것을 한 번 고른다."""
    dataset = load_dataset()
    embedder = OpenAICompatEmbedder(
        client=client, base_url=arguments.base_url, model=arguments.embedding_model, timeout=arguments.timeout
    )
    prepared = []
    for name in arguments.case:
        case = CASES[name]
        request = case_request(dataset, case)
        prepared.append((case, request, await memory_context(embedder, dataset, request, current_thresholds())))
    return prepared


async def run_all(arguments: argparse.Namespace) -> tuple[list[MemoryTrial], str]:
    """모델마다, 장면마다, 문체마다, 방식마다 --repeat 번씩 서술하게 한다. 하나씩 끝나는 대로 찍는다."""
    trials = []
    async with httpx.AsyncClient() as client:
        prepared = await prepare(client, arguments)
        contexts = describe_contexts([(case, context) for case, _, context in prepared])
        print(contexts, '\n', flush=True)
        for model in arguments.model:
            provider = make_provider(client, arguments, model)
            if not arguments.no_warmup:
                await warm_up(provider)
            for case, request, context in prepared:
                for style in arguments.style:
                    for mode in arguments.memory:
                        for _ in range(arguments.repeat):
                            trial = await run_trial(
                                provider,
                                case,
                                request,
                                MemoryMode(mode),
                                context,
                                NarrationStyle(style),
                                arguments.live,
                            )
                            print(describe(trial), flush=True)
                            trials.append(trial)
    return trials, contexts


def main() -> None:
    """명령줄을 읽고, 돌리고, 표를 찍고, 원하면 파일로 남긴다."""
    arguments = read_arguments()
    try:
        trials, contexts = asyncio.run(run_all(arguments))
    except ProviderError as error:
        print(f'임베딩 모델을 부르지 못했다: {error}')
        raise SystemExit(1) from error
    print(tally(trials))
    if arguments.out is not None:
        body = '\n'.join([contexts, '', tally(trials), '', *(describe(trial) for trial in trials)])
        arguments.out.write_text(body, encoding='utf-8')
        print(f'\n저장했다: {arguments.out}')


if __name__ == '__main__':
    main()
