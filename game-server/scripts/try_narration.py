# game-server/scripts/try_narration.py

"""
실제 언어 모델로 서술을 써 본다. 서버도 DB 도 쓰지 않고, 여기 적어 둔 예시 라운드 하나로.

모델을 고르거나(비교), 추론을 켜고 끈 차이나 문체마다의 차이, 로어북을 넣고 뺀 차이를 볼 때 쓴다.
자동 테스트가 아니라서 CI 에서 돌지 않는다.
서버가 쓰는 것과 같은 조립(app/rounds/prompt.py), provider, 장면 검사를 그대로 거친다.

    uv run python -m scripts.try_narration --model gemma4:26b
    uv run python -m scripts.try_narration --model gemma4:26b qwen3.6:27b --reasoning none low --out report.md
    uv run python -m scripts.try_narration --model gemma4:26b-a4b-it-qat --style classic dopamine literary
    uv run python -m scripts.try_narration --model gemma4:26b-a4b-it-qat --style dopamine --repeat 3
    uv run python -m scripts.try_narration --model gemma4:26b-a4b-it-qat --live
    uv run python -m scripts.try_narration --model gemma4:26b-a4b-it-qat --lore off on noise --repeat 5

game-server 폴더에서 -m 으로 돌린다. 그래야 app 을 찾는다.

모델마다 먼저 아주 짧은 요청을 보내 메모리에 올려 둔다(--no-warmup 으로 끈다).
올리는 시간이 섞이면 속도를 견줄 수 없다.
한 모델이 실패해도 나머지는 계속 돈다. 끝에 한눈에 보는 표를 찍고, --out 을 주면 표와 장면을 UTF-8 파일로도 남긴다.
장면마다 기계로 잡을 수 있는 것을 "확인할 것"으로 표시한다. 보낸 적 없는 숫자, 숨긴 설정의 낱말, 문체 예시의 낱말,
섞여 든 한자와 영어, 지난 행동·버릇의 낱말(선언한 행동이 바뀌었나), 따옴표 대사(PC 가 말했나),
설정에만 있는 이름(플레이어가 모르는 이름을 먼저 꺼냈나).
--repeat 로 같은 것을 여러 번 돌린다. 한 번의 결과는 운일 수 있다.
끝에 같은 설정으로 돌린 것끼리 묶어 몇 번 중 몇 번 나왔는지 세는 표를 찍는다.
판단은 사람이 한다.
답은 흘려 받는다. 첫 글이 오기까지의 시간(앉은 사람이 기다리는 시간)을 따로 잰다. --live 를 주면 오는 대로 찍는다.

--lore 는 로어북을 넣는 방식이다(evals/lore/narration.py). off 는 넣지 않고, on 은 서버와 같은 규칙과 임베딩 모델
(--embedding-model, 같은 주소)로 평가 데이터(evals/lore/chase.yaml)에서 고른 항목을, noise 는 상관없는 항목을 넣는다.
장면마다 로어북에서만 올 수 있는 낱말을 썼는지(on 낱말), 상관없는 항목의 낱말에 끌려갔는지(noise 낱말)를 적는다.

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
from app.ai.openai_embedder import OpenAICompatEmbedder
from app.ai.provider import ChatMessage, Completion, GenerationParams, ProviderError, Reasoning, Role
from app.assets.models import NarrationStyle
from app.rounds.llm_narrator import NARRATION_PARAMS, NarrationError, accept_completion
from app.rounds.narrator import Impact, Move, NarrationRequest, PastRound, StoryContext, Verdict
from app.rounds.prompt import build_messages
from evals.lore.dataset import DEFAULT_PATH, load_dataset
from evals.lore.narration import (
    LoreMode,
    LoreSets,
    describe_sets,
    lore_only_words,
    lore_sets,
    notes_for,
    prompt_text,
    used_words,
)

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

# 숨긴 설정의 낱말. GM 메모에 있고, 로어북을 넣으면 악역영애의 항목(비올레타)에도 있다.
# 장면에 나오면 비밀을 흘렸을 수 있다.
# '경찰' 은 넣지 않는다. 장면에 사이렌이 있어 경찰차가 나오는 것은 자연스럽다(첫 비교에서 오탐이 났다)
LEAK_WORDS = ('끄나풀', '정보원')
# 문체 예시(app/rounds/prompt.py 의 STYLE_RULES)에만 있는 낱말. 장면에 나오면 예시의 내용이 새어 든 것일 수 있다
SAMPLE_WORDS = ('국자', '식당', '단골', '외투', '숟가락', '빗')
# 지난 라운드의 행동과 로어북의 버릇에만 있는 낱말. 토르빈은 1 라운드에 망치로 차단기를 내려쳤고, 로어북에는
# "무엇이든 망치로 두드려 해결하려 한다"가 있다. 이번 라운드의 선언은 "리무진을 들어 올린다"다.
# 장면에 나오면 선언한 행동이 바뀌었을 수 있다(#100 의 측정). 행동을 꾸미는 데 쓴 것일 수도 있다. 사람이 본다
PAST_ACTION_WORDS = ('망치', '내려치', '내리치', '두드')
# 따옴표 대사. NPC 의 대사는 괜찮다. PC 의 대사인지는 사람이 본다
QUOTE = re.compile(r'["“][^"”\n]*["”]')
# "확인할 것"의 이름들. 묶어 세는 표가 이 이름으로 센다
HINT_NUMBER = '보낸 적 없는 숫자'
HINT_LEAK = '숨긴 설정의 낱말'
HINT_SAMPLE = '문체 예시의 낱말'
HINT_HANZI = '한자'
HINT_LATIN = '영어 낱말'
HINT_PAST = '지난 행동·버릇의 낱말'
HINT_QUOTE = '따옴표 대사'
HINT_NAME = '설정에만 있는 이름'
# 묶어 세는 표에 세는 것들
TALLIED_HINTS = (HINT_PAST, HINT_QUOTE, HINT_NAME, HINT_LEAK)
# 한국어 장면에 섞여 들면 안 되는 글자. 다국어 모델이 가끔 중국어나 영어를 섞는다
HANZI = re.compile(r'[\u4e00-\u9fff]')
LATIN_WORD = re.compile(r'[A-Za-z]{3,}')
NUMBER = re.compile(r'\d+')

# 모델을 메모리에 올리기만 하는 요청. 답은 한 토큰이면 된다
WARMUP_MESSAGES = [ChatMessage(Role.USER, '안녕')]
WARMUP_PARAMS = GenerationParams(max_tokens=1, temperature=0.0)


@dataclass(frozen=True)
class Trial:
    """
    모델 하나, 추론 수준 하나, 문체 하나로 서술해 본 결과.

    problem 은 provider 의 실패나 장면으로 받지 않은 이유다. first_text 는 첫 글이 오기까지 걸린 시간(초)이다.
    lore 는 로어북을 넣은 방식, notes 는 넣은 항목의 수다.
    lore_used, noise_used 는 장면에 나온 낱말 중 로어북(on 의 항목, noise 의 항목)에서만 올 수 있는 것이다.
    """

    model: str
    reasoning: Reasoning
    style: NarrationStyle
    seconds: float
    first_text: float | None = None
    completion: Completion | None = None
    scene: str | None = None
    problem: str | None = None
    lore: LoreMode = LoreMode.OFF
    notes: int = 0
    lore_used: tuple[str, ...] = ()
    noise_used: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()


def read_arguments() -> argparse.Namespace:
    """명령줄의 값을 읽는다."""
    parser = argparse.ArgumentParser(description='실제 언어 모델로 서술을 써 본다.')
    parser.add_argument('--model', required=True, nargs='+', help='모델 이름. 여럿을 띄어 적는다')
    parser.add_argument('--reasoning', nargs='+', default=['none'], choices=[level.value for level in Reasoning])
    parser.add_argument('--style', nargs='+', default=['classic'], choices=[style.value for style in NarrationStyle])
    parser.add_argument('--lore', nargs='+', default=['off'], choices=[mode.value for mode in LoreMode])
    parser.add_argument('--embedding-model', default='bge-m3', help='--lore on 의 항목을 고를 임베딩 모델')
    parser.add_argument('--repeat', type=int, default=1, help='같은 모델, 추론, 문체, 로어북으로 몇 번 돌릴까')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1', help='OpenAI 모양의 주소')
    parser.add_argument('--timeout', type=float, default=300.0, help='한 요청을 기다리는 시간(초)')
    parser.add_argument('--no-reasoning-field', action='store_true', help='추론 수준을 보내지 않는다')
    parser.add_argument('--no-warmup', action='store_true', help='모델을 미리 올리지 않는다')
    parser.add_argument('--live', action='store_true', help='흘려 받는 글을 오는 대로 찍는다')
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


@dataclass
class Watch:
    """흘려 받는 글을 지켜본다. 첫 글이 온 때를 적고, live 면 오는 대로 찍는다. provider 의 on_text 에 꽂는다."""

    started: float
    live: bool
    first: float | None = None

    def __call__(self, text: str) -> None:
        if self.first is None:
            self.first = time.perf_counter() - self.started
        if self.live:
            print(text, end='', flush=True)


def lore_hits(scene: str, style: NarrationStyle, sets: LoreSets | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """장면에 나온 on 의 낱말과 noise 의 낱말. 로어북을 뺀 프롬프트에 없는 것만 센다. 항목이 없으면 비어 있다."""
    if sets is None:
        return (), ()
    base = prompt_text(build_messages(replace(REQUEST, style=style)))
    on = used_words(scene, lore_only_words(sets.on, base))
    noise = used_words(scene, lore_only_words(sets.noise, base))
    return tuple(on), tuple(noise)


async def run_trial(
    provider: OpenAICompatProvider,
    reasoning: Reasoning,
    style: NarrationStyle,
    live: bool = False,
    lore: LoreMode = LoreMode.OFF,
    sets: LoreSets | None = None,
) -> Trial:
    """예시 라운드를 한 번 서술하게 한다. 실패해도 예외를 올리지 않고 결과에 적는다."""
    params = replace(NARRATION_PARAMS, reasoning=reasoning)
    notes = notes_for(lore, sets) if sets is not None else []
    messages = build_messages(replace(REQUEST, style=style, lore=notes))
    watch = Watch(started=time.perf_counter(), live=live)
    base = {'lore': lore, 'notes': len(notes)}
    try:
        completion = await provider.complete(messages, params, watch)
    except ProviderError as error:
        seconds = time.perf_counter() - watch.started
        return Trial(provider.model, reasoning, style, seconds, watch.first, problem=f'provider 실패: {error}', **base)
    seconds = time.perf_counter() - watch.started
    try:
        scene = accept_completion(completion)
    except NarrationError as error:
        problem = f'장면으로 받지 않음: {error}'
        return Trial(
            provider.model, reasoning, style, seconds, watch.first, completion=completion, problem=problem, **base
        )
    lore_used, noise_used = lore_hits(scene, style, sets)
    hints = tuple(find_hints(scene, sets, style))
    return Trial(
        provider.model,
        reasoning,
        style,
        seconds,
        watch.first,
        completion=completion,
        scene=scene,
        lore_used=lore_used,
        noise_used=noise_used,
        hints=hints,
        **base,
    )


def seconds_or_dash(value: float | None) -> str:
    """초를 소수 한 자리로. 없으면 '-'."""
    return '-' if value is None else f'{value:.1f}'


def numbers_sent() -> set[str]:
    """모델에게 보낸 글에 들어 있는 숫자들. 장면의 숫자는 이 안에 있어야 한다."""
    return {number for message in build_messages(REQUEST) for number in NUMBER.findall(message.content)}


def unseen_names(scene: str, style: NarrationStyle, sets: LoreSets | None) -> list[str]:
    """
    장면에 나온 로어북 항목의 이름 중 로어북을 뺀 프롬프트에는 없는 것. 플레이어가 아직 모르는 이름이다.

    인물은 장면에 이미 나온 호칭으로 부르기로 했다(narration-5). 항목이 없으면 빈 목록이다.
    """
    if sets is None:
        return []
    base = prompt_text(build_messages(replace(REQUEST, style=style)))
    return [entry.name for entry in [*sets.on, *sets.noise] if entry.name not in base and entry.name in scene]


def find_hints(scene: str, sets: LoreSets | None = None, style: NarrationStyle = NarrationStyle.CLASSIC) -> list[str]:
    """장면에서 기계로 잡을 수 있는 의심거리. 있다고 틀린 것은 아니다. 사람이 읽고 판단한다."""
    hints = []
    made_up = sorted(set(NUMBER.findall(scene)) - numbers_sent(), key=int)
    if made_up:
        hints.append(f'{HINT_NUMBER}({", ".join(made_up)})')
    leaked = [word for word in LEAK_WORDS if word in scene]
    if leaked:
        hints.append(f'{HINT_LEAK}({", ".join(leaked)})')
    borrowed = [word for word in SAMPLE_WORDS if word in scene]
    if borrowed:
        hints.append(f'{HINT_SAMPLE}({", ".join(borrowed)})')
    hanzi = HANZI.findall(scene)
    if hanzi:
        hints.append(f'{HINT_HANZI} {len(hanzi)}자')
    latin = LATIN_WORD.findall(scene)
    if latin:
        hints.append(f'{HINT_LATIN} {len(latin)}개')
    past = [word for word in PAST_ACTION_WORDS if word in scene]
    if past:
        hints.append(f'{HINT_PAST}({", ".join(past)})')
    quotes = QUOTE.findall(scene)
    if quotes:
        hints.append(f'{HINT_QUOTE} {len(quotes)}개')
    names = unseen_names(scene, style, sets)
    if names:
        hints.append(f'{HINT_NAME}({", ".join(names)})')
    return hints


def describe(trial: Trial) -> str:
    """결과 하나를 읽기 좋은 글로."""
    head = f'## {trial.model} / 추론 {trial.reasoning.value} / 문체 {trial.style.value} / 로어북 {trial.lore.value}'
    lines = [f'{head} / {trial.seconds:.1f}초 (첫 글 {seconds_or_dash(trial.first_text)}초)']
    if trial.completion is not None:
        completion = trial.completion
        tokens = f'토큰: 입력 {completion.input_tokens}, 출력 {completion.output_tokens}'
        lines.append(f'{tokens} / 멈춘 이유: {completion.finish_reason}')
    if trial.problem is not None:
        lines.append(trial.problem)
    if trial.scene is not None:
        hints = trial.hints
        lines.append(f'장면 {len(trial.scene)}자' + (f' / 확인할 것: {", ".join(hints)}' if hints else ''))
        if trial.lore != LoreMode.OFF or trial.lore_used or trial.noise_used:
            lines.append(f'넣은 항목 {trial.notes}개 / {words_line(trial)}')
        lines.extend(['', trial.scene])
    lines.append('')
    return '\n'.join(lines)


def words_line(trial: Trial) -> str:
    """장면에 나온 로어북의 낱말들. on 의 것과 noise 의 것."""
    return f'on 낱말 {list(trial.lore_used)} / noise 낱말 {list(trial.noise_used)}'


def summarize(trials: list[Trial]) -> str:
    """모든 결과를 한눈에 보는 표(마크다운)."""
    rows = [
        '| 모델 | 추론 | 문체 | 로어북 | 초 | 첫 글(초) | 입력 토큰 | 출력 토큰 | 장면 '
        '| on 낱말 | noise 낱말 | 확인할 것 |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for trial in trials:
        tokens = (trial.completion.input_tokens, trial.completion.output_tokens) if trial.completion else ('-', '-')
        scene = f'{len(trial.scene)}자' if trial.scene is not None else trial.problem
        hints = ', '.join(trial.hints) if trial.scene is not None else '-'
        head = f'| {trial.model} | {trial.reasoning.value} | {trial.style.value} | {trial.lore.value} |'
        timing = f' {trial.seconds:.1f} | {seconds_or_dash(trial.first_text)} | {tokens[0]} | {tokens[1]} |'
        words = f' {len(trial.lore_used)} | {len(trial.noise_used)} |'
        rows.append(f'{head}{timing} {scene} |{words} {hints} |')
    return '\n'.join(rows)


def has_hint(trial: Trial, name: str) -> bool:
    """이 결과에 그 이름의 "확인할 것"이 있는가."""
    return any(hint.startswith(name) for hint in trial.hints)


def average(values: list[int]) -> str:
    """평균을 소수 한 자리로. 값이 없으면 '-'."""
    return f'{sum(values) / len(values):.1f}' if values else '-'


def tally_row(group: list[Trial]) -> str:
    """같은 설정으로 돌린 결과들을 센 한 줄. 장면이 나온 것 중 몇 번에 그것이 있었나."""
    first = group[0]
    scenes = [trial for trial in group if trial.scene is not None]
    counts = [f'{sum(has_hint(trial, name) for trial in scenes)}/{len(scenes)}' for name in TALLIED_HINTS]
    tokens = [trial.completion.input_tokens for trial in scenes if trial.completion and trial.completion.input_tokens]
    cells = [
        first.model,
        first.reasoning.value,
        first.style.value,
        first.lore.value,
        str(len(group)),
        str(len(group) - len(scenes)),
        *counts,
        average([len(trial.lore_used) for trial in scenes]),
        average([len(trial.noise_used) for trial in scenes]),
        average(tokens),
    ]
    return '| ' + ' | '.join(cells) + ' |'


def tally(trials: list[Trial]) -> str:
    """같은 모델, 추론, 문체, 로어북으로 돌린 것끼리 묶어 센 표(마크다운). 돌린 차례대로."""
    groups: dict[tuple, list[Trial]] = {}
    for trial in trials:
        groups.setdefault((trial.model, trial.reasoning, trial.style, trial.lore), []).append(trial)
    header = ['모델', '추론', '문체', '로어북', '횟수', '실패', *TALLIED_HINTS, 'on 낱말', 'noise 낱말', '입력 토큰']
    rows = ['| ' + ' | '.join(header) + ' |', '| ' + ' | '.join('---' for _ in header) + ' |']
    rows.extend(tally_row(group) for group in groups.values())
    return '\n'.join(rows)


async def prepare_lore(client: httpx.AsyncClient, arguments: argparse.Namespace) -> LoreSets | None:
    """로어북을 넣는 방식이 있으면 넣을 항목들을 한 번 고른다. off 뿐이면 None."""
    if all(LoreMode(mode) == LoreMode.OFF for mode in arguments.lore):
        return None
    embedder = OpenAICompatEmbedder(
        client=client, base_url=arguments.base_url, model=arguments.embedding_model, timeout=arguments.timeout
    )
    return await lore_sets(embedder, load_dataset(DEFAULT_PATH).entries, REQUEST)


async def run_all(arguments: argparse.Namespace) -> tuple[list[Trial], LoreSets | None]:
    """모델마다, 추론 수준마다, 문체마다, 로어북마다 --repeat 번씩 서술하게 한다. 하나씩 끝나는 대로 찍는다."""
    trials = []
    async with httpx.AsyncClient() as client:
        sets = await prepare_lore(client, arguments)
        if sets is not None:
            print(describe_sets(sets), '\n', flush=True)
        for model in arguments.model:
            provider = make_provider(client, arguments, model)
            if not arguments.no_warmup:
                await warm_up(provider)
            for level in arguments.reasoning:
                for style in arguments.style:
                    for mode in arguments.lore:
                        for _ in range(arguments.repeat):
                            trial = await run_trial(
                                provider, Reasoning(level), NarrationStyle(style), arguments.live, LoreMode(mode), sets
                            )
                            if arguments.live:
                                print('\n')
                            print(describe(trial), flush=True)
                            trials.append(trial)
    return trials, sets


def write_report(path: Path, trials: list[Trial], sets: LoreSets | None = None) -> None:
    """표와 장면 전부를 UTF-8 파일로 남긴다. 콘솔의 인코딩과 상관없이 한글이 깨지지 않는다."""
    head = [describe_sets(sets), ''] if sets is not None else []
    body = '\n'.join([*head, tally(trials), '', summarize(trials), '', *(describe(trial) for trial in trials)])
    path.write_text(body, encoding='utf-8')


def main() -> None:
    """명령줄을 읽고, 돌리고, 표를 찍고, 원하면 파일로 남긴다."""
    arguments = read_arguments()
    trials, sets = asyncio.run(run_all(arguments))
    print(summarize(trials))
    print()
    print(tally(trials))
    if arguments.out is not None:
        write_report(arguments.out, trials, sets)
        print(f'\n저장했다: {arguments.out}')


if __name__ == '__main__':
    main()
