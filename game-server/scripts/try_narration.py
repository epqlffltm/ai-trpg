# game-server/scripts/try_narration.py

"""
실제 언어 모델로 서술을 써 본다. 서버도 DB 도 쓰지 않고, 여기 적어 둔 예시 라운드 하나로.

모델을 고르거나(비교), 추론을 켜고 끈 차이를 볼 때 쓴다. 자동 테스트가 아니라서 CI 에서 돌지 않는다.
서버가 쓰는 것과 같은 조립(app/rounds/prompt.py), provider, 장면 검사를 그대로 거친다.

    uv run python -m scripts.try_narration --model gemma4:26b
    uv run python -m scripts.try_narration --model gemma4:26b qwen3.6:27b --reasoning none low --out report.md

game-server 폴더에서 -m 으로 돌린다. 그래야 app 을 찾는다.

모델마다 먼저 아주 짧은 요청을 보내 메모리에 올려 둔다(--no-warmup 으로 끈다).
올리는 시간이 섞이면 속도를 견줄 수 없다.
한 모델이 실패해도 나머지는 계속 돈다. 끝에 한눈에 보는 표를 찍고, --out 을 주면 표와 장면을 UTF-8 파일로도 남긴다.
장면마다 기계로 잡을 수 있는 것(보낸 적 없는 숫자, GM 메모의 낱말, 섞여 든 한자와 영어)을 "확인할 것"으로 표시한다.
판단은 사람이 한다.

예시는 공개 저장소에 올라가도 되는 개그 설정이다(악역영애, 엘프 폭주족, 열일곱 행성의 추격전).
"""

import argparse
import asyncio
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path

import httpx

from app.ai.openai_compat import OpenAICompatProvider
from app.ai.provider import ChatMessage, Completion, GenerationParams, ProviderError, Reasoning, Role
from app.rounds.llm_narrator import NARRATION_PARAMS, NarrationError, accept_completion
from app.rounds.narrator import Impact, Move, NarrationRequest, PastRound, StoryContext, Verdict
from app.rounds.prompt import build_messages

STORY = StoryContext(
    title='열일곱 행성 추격전',
    rating='all',
    guide='추격은 언제나 바이크로 한다. 긴장감 있게, 그러나 가끔은 웃기게 진행한다.',
    setting='열일곱 개의 행성이 우주 고속도로로 이어져 있다. 엘프 폭주족은 은하에서 가장 빠른 바이크를 탄다.',
    gm_notes='악역영애는 사실 경찰의 끄나풀이다. 아직 드러내지 않는다.',
)

HISTORY = [
    PastRound(
        number=1,
        scene='세 번째 행성의 톨게이트. 악역영애의 금빛 리무진이 엘프 폭주족의 길을 막아섰다.',
        lines=['리엔: 바이크의 시동을 건다.', '토르빈: 톨게이트 차단기를 망치로 내려친다.'],
    ),
]

REQUEST = NarrationRequest(
    round_number=2,
    scene='차단기가 부서지자 사이렌이 울린다. 리무진의 창문이 내려가고, 악역영애가 부채를 접으며 웃는다.',
    moves=[
        Move(
            '리엔',
            '리무진 옆을 스치듯 빠져나가며 악역영애의 부채를 낚아챈다.',
            verdict=Verdict(
                ability='민첩', difficulty='어려움', roll=17, modifier=3, total=20, target=20, success=True
            ),
        ),
        Move(
            '토르빈',
            '드워프의 근력으로 리무진을 들어 올려 길가로 치운다.',
            verdict=Verdict(
                ability='근력',
                difficulty='매우 어려움',
                roll=6,
                modifier=4,
                total=10,
                target=25,
                success=False,
                impact=Impact(kind='damage', character_name='토르빈', amount=5, hp=7, max_hp=12, downed=False),
            ),
        ),
    ],
    story=STORY,
    history=HISTORY,
)

# GM 메모에만 있는 낱말. 장면에 나오면 메모를 흘렸을 수 있다.
# '경찰' 은 넣지 않는다. 장면에 사이렌이 있어 경찰차가 나오는 것은 자연스럽다(첫 비교에서 오탐이 났다)
LEAK_WORDS = ('끄나풀', '정보원')
# 한국어 장면에 섞여 들면 안 되는 글자. 다국어 모델이 가끔 중국어나 영어를 섞는다
HANZI = re.compile(r'[\u4e00-\u9fff]')
LATIN_WORD = re.compile(r'[A-Za-z]{3,}')
NUMBER = re.compile(r'\d+')

# 모델을 메모리에 올리기만 하는 요청. 답은 한 토큰이면 된다
WARMUP_MESSAGES = [ChatMessage(Role.USER, '안녕')]
WARMUP_PARAMS = GenerationParams(max_tokens=1, temperature=0.0)


@dataclass(frozen=True)
class Trial:
    """모델 하나, 추론 수준 하나로 서술해 본 결과. problem 은 provider 의 실패나 장면으로 받지 않은 이유다."""

    model: str
    reasoning: Reasoning
    seconds: float
    completion: Completion | None = None
    scene: str | None = None
    problem: str | None = None


def read_arguments() -> argparse.Namespace:
    """명령줄의 값을 읽는다."""
    parser = argparse.ArgumentParser(description='실제 언어 모델로 서술을 써 본다.')
    parser.add_argument('--model', required=True, nargs='+', help='모델 이름. 여럿을 띄어 적는다')
    parser.add_argument('--reasoning', nargs='+', default=['none'], choices=[level.value for level in Reasoning])
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1', help='OpenAI 모양의 주소')
    parser.add_argument('--timeout', type=float, default=300.0, help='한 요청을 기다리는 시간(초)')
    parser.add_argument('--no-reasoning-field', action='store_true', help='추론 수준을 보내지 않는다')
    parser.add_argument('--no-warmup', action='store_true', help='모델을 미리 올리지 않는다')
    parser.add_argument('--out', type=Path, help='표와 장면을 남길 파일(UTF-8)')
    return parser.parse_args()


def make_provider(client: httpx.AsyncClient, arguments: argparse.Namespace, model: str) -> OpenAICompatProvider:
    """명령줄의 값으로 provider 를 만든다."""
    return OpenAICompatProvider(
        client=client,
        base_url=arguments.base_url,
        model=model,
        timeout=arguments.timeout,
        supports_reasoning=not arguments.no_reasoning_field,
    )


async def warm_up(provider: OpenAICompatProvider) -> None:
    """모델을 메모리에 올려 둔다. 실패해도 넘어간다. 진짜 요청에서 다시 실패하면 그때 적힌다."""
    try:
        await provider.complete(WARMUP_MESSAGES, WARMUP_PARAMS)
    except ProviderError:
        return


async def run_trial(provider: OpenAICompatProvider, reasoning: Reasoning) -> Trial:
    """예시 라운드를 한 번 서술하게 한다. 실패해도 예외를 올리지 않고 결과에 적는다."""
    params = replace(NARRATION_PARAMS, reasoning=reasoning)
    started = time.perf_counter()
    try:
        completion = await provider.complete(build_messages(REQUEST), params)
    except ProviderError as error:
        return Trial(provider.model, reasoning, time.perf_counter() - started, problem=f'provider 실패: {error}')
    seconds = time.perf_counter() - started
    try:
        scene = accept_completion(completion)
    except NarrationError as error:
        return Trial(provider.model, reasoning, seconds, completion=completion, problem=f'장면으로 받지 않음: {error}')
    return Trial(provider.model, reasoning, seconds, completion=completion, scene=scene)


def numbers_sent() -> set[str]:
    """모델에게 보낸 글에 들어 있는 숫자들. 장면의 숫자는 이 안에 있어야 한다."""
    return {number for message in build_messages(REQUEST) for number in NUMBER.findall(message.content)}


def find_hints(scene: str) -> list[str]:
    """장면에서 기계로 잡을 수 있는 의심거리. 있다고 틀린 것은 아니다. 사람이 읽고 판단한다."""
    hints = []
    made_up = sorted(set(NUMBER.findall(scene)) - numbers_sent(), key=int)
    if made_up:
        hints.append(f'보낸 적 없는 숫자({", ".join(made_up)})')
    leaked = [word for word in LEAK_WORDS if word in scene]
    if leaked:
        hints.append(f'GM 메모의 낱말({", ".join(leaked)})')
    hanzi = HANZI.findall(scene)
    if hanzi:
        hints.append(f'한자 {len(hanzi)}자')
    latin = LATIN_WORD.findall(scene)
    if latin:
        hints.append(f'영어 낱말 {len(latin)}개')
    return hints


def describe(trial: Trial) -> str:
    """결과 하나를 읽기 좋은 글로."""
    lines = [f'## {trial.model} / 추론 {trial.reasoning.value} / {trial.seconds:.1f}초']
    if trial.completion is not None:
        completion = trial.completion
        tokens = f'토큰: 입력 {completion.input_tokens}, 출력 {completion.output_tokens}'
        lines.append(f'{tokens} / 멈춘 이유: {completion.finish_reason}')
    if trial.problem is not None:
        lines.append(trial.problem)
    if trial.scene is not None:
        hints = find_hints(trial.scene)
        lines.append(f'장면 {len(trial.scene)}자' + (f' / 확인할 것: {", ".join(hints)}' if hints else ''))
        lines.extend(['', trial.scene])
    lines.append('')
    return '\n'.join(lines)


def summarize(trials: list[Trial]) -> str:
    """모든 결과를 한눈에 보는 표(마크다운)."""
    rows = ['| 모델 | 추론 | 초 | 출력 토큰 | 장면 | 확인할 것 |', '| --- | --- | --- | --- | --- | --- |']
    for trial in trials:
        output = trial.completion.output_tokens if trial.completion else '-'
        scene = f'{len(trial.scene)}자' if trial.scene is not None else trial.problem
        hints = ', '.join(find_hints(trial.scene)) if trial.scene is not None else '-'
        rows.append(f'| {trial.model} | {trial.reasoning.value} | {trial.seconds:.1f} | {output} | {scene} | {hints} |')
    return '\n'.join(rows)


async def run_all(arguments: argparse.Namespace) -> list[Trial]:
    """모델마다, 추론 수준마다 한 번씩 서술하게 한다. 하나씩 끝나는 대로 찍는다."""
    trials = []
    async with httpx.AsyncClient() as client:
        for model in arguments.model:
            provider = make_provider(client, arguments, model)
            if not arguments.no_warmup:
                await warm_up(provider)
            for level in arguments.reasoning:
                trial = await run_trial(provider, Reasoning(level))
                print(describe(trial), flush=True)
                trials.append(trial)
    return trials


def write_report(path: Path, trials: list[Trial]) -> None:
    """표와 장면 전부를 UTF-8 파일로 남긴다. 콘솔의 인코딩과 상관없이 한글이 깨지지 않는다."""
    body = '\n'.join([summarize(trials), '', *(describe(trial) for trial in trials)])
    path.write_text(body, encoding='utf-8')


def main() -> None:
    """명령줄을 읽고, 돌리고, 표를 찍고, 원하면 파일로 남긴다."""
    arguments = read_arguments()
    trials = asyncio.run(run_all(arguments))
    print(summarize(trials))
    if arguments.out is not None:
        write_report(arguments.out, trials)
        print(f'\n저장했다: {arguments.out}')


if __name__ == '__main__':
    main()
