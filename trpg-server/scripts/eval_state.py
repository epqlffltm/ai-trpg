# trpg-server/scripts/eval_state.py

"""
서술이 엔진이 정한 상태를 지키는지 실제 언어 모델로 잰다(#111 ④). 서버도 DB 도 쓰지 않는다.

장면은 evals/state/cases.py 에 있다. 쓰러진 NPC, 죽은 NPC, 부상(PC, NPC), 치료(다 나음, 덧남), 지목(틀림, 맞음),
맵(숨은 길 옆, 못 찾은 찾기, 찾은 찾기, 간 가기, 못 간 가기).
장면마다 --repeat 번(기본 3) 서술하게 하고, 낱말로 어림하는 검사가 몇 번 걸렸는지 센다. 걸린 장면은 사람이 읽는다.
한 번의 결과는 운일 수 있어서 여러 번 돌린다.

    uv run python -m scripts.eval_state
    uv run python -m scripts.eval_state --repeat 5 --out $HOME\\state-eval.md
    uv run python -m scripts.eval_state --case naming_wrong naming_right --repeat 10
    uv run python -m scripts.eval_state --case map_hidden map_search_failed map_search_found --repeat 10
    uv run python -m scripts.eval_state --model gemma4:26b-a4b-it-qat qwen3.6:27b
    uv run python -m scripts.eval_state --fake

trpg-server 폴더에서 -m 으로 돌린다. 모델의 주소는 기본이 집의 Ollama(127.0.0.1)다.
--fake 는 모델 없이 정해 둔 글 하나로 돈다. 검사가 걸리는지, 스크립트가 끝까지 도는지 볼 때 쓴다.
--rescore 는 모델을 부르지 않고 남겨 둔 보고서(--out 의 파일)를 지금의 검사로 다시 센다. 검사의 낱말을 고친 뒤에 쓴다.

    uv run python -m scripts.eval_state --rescore $HOME\\state-eval.md --out $HOME\\state-eval-rescored.md
자동 테스트가 아니라서 CI 에서 돌지 않는다.
"""

import argparse
import asyncio
from pathlib import Path

import httpx
from ai_core.fake import FakeProvider
from ai_core.provider import LLMProvider, Reasoning

from evals.state.cases import CASE_NAMES, CASES, StateCase
from evals.state.report import describe, full_report, read_report, tally_lines, total_line
from evals.state.runner import Trial, rescore, run_cases
from scripts.try_narration import make_provider, warm_up

# 기본 모델. 서버의 기본 서술 모델과 같다(#85 의 비교)
DEFAULT_MODEL = 'gemma4:26b-a4b-it-qat'
# --fake 가 돌려주는 글. 쓰러진 악역영애가 말하고, 진짜 이름을 흘린다. 검사가 걸리는 것을 본다
FAKE_SCENE = '쓰러진 악역영애가 눈을 뜨며 "아직 끝나지 않았어." 하고 중얼거렸다. 비올레타의 부채가 바닥에 떨어졌다.'


def read_arguments() -> argparse.Namespace:
    """명령줄의 값을 읽는다."""
    parser = argparse.ArgumentParser(description='서술이 엔진이 정한 상태를 지키는지 잰다.')
    parser.add_argument('--model', nargs='+', default=[DEFAULT_MODEL], help='모델 이름. 여럿을 띄어 적는다')
    parser.add_argument('--case', nargs='+', default=list(CASE_NAMES), choices=CASE_NAMES, help='돌릴 장면')
    parser.add_argument('--repeat', type=int, default=3, help='장면마다 몇 번 서술하게 할까')
    parser.add_argument('--reasoning', default='none', choices=[level.value for level in Reasoning])
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1', help='OpenAI 모양의 주소')
    parser.add_argument('--timeout', type=float, default=300.0, help='한 요청을 기다리는 시간(초)')
    parser.add_argument('--no-reasoning-field', action='store_true', help='추론 수준을 보내지 않는다')
    parser.add_argument('--no-warmup', action='store_true', help='모델을 미리 올리지 않는다')
    parser.add_argument('--fake', action='store_true', help='모델 없이 정해 둔 글로 돈다')
    parser.add_argument('--rescore', type=Path, help='모델을 부르지 않고 이 보고서를 다시 센다')
    parser.add_argument('--out', type=Path, help='표와 장면을 남길 파일(UTF-8)')
    return parser.parse_args()


def chosen_cases(names: list[str]) -> tuple[StateCase, ...]:
    """고른 장면들. 적어 둔 차례대로다(명령줄의 차례가 아니라)."""
    return tuple(case for case in CASES if case.name in names)


def print_trial(trial: Trial) -> None:
    """하나 끝날 때마다 찍는다. 오래 도는 동안 멈춘 것이 아님을 보인다."""
    print(describe(trial), flush=True)


async def providers(client: httpx.AsyncClient, arguments: argparse.Namespace) -> list[LLMProvider]:
    """돌릴 provider 들. --fake 면 가짜 하나. 아니면 모델마다 하나를 만들어 메모리에 올려 둔다."""
    if arguments.fake:
        return [FakeProvider(reply=FAKE_SCENE)]
    made = [make_provider(client, arguments, model) for model in arguments.model]
    if not arguments.no_warmup:
        for provider in made:
            await warm_up(provider)
    return made


async def run_all(arguments: argparse.Namespace) -> list[Trial]:
    """모델마다 고른 장면을 --repeat 번씩 돌린다."""
    cases = chosen_cases(arguments.case)
    trials = []
    async with httpx.AsyncClient() as client:
        for provider in await providers(client, arguments):
            trials.extend(
                await run_cases(provider, cases, arguments.repeat, Reasoning(arguments.reasoning), print_trial)
            )
    return trials


def collect(arguments: argparse.Namespace) -> list[Trial]:
    """다시 셀 보고서가 있으면 그것을, 아니면 모델을 불러 결과를 모은다."""
    if arguments.rescore is not None:
        return rescore(read_report(arguments.rescore.read_text(encoding='utf-8')))
    return asyncio.run(run_all(arguments))


def main() -> None:
    """명령줄을 읽고, 돌리거나 다시 세고, 표를 찍고, 원하면 파일로 남긴다."""
    arguments = read_arguments()
    trials = collect(arguments)
    print('\n'.join(tally_lines(trials)))
    print()
    print(total_line(trials))
    if arguments.out is not None:
        arguments.out.write_text(full_report(trials), encoding='utf-8')
        print(f'\n저장했다: {arguments.out}')


if __name__ == '__main__':
    main()
