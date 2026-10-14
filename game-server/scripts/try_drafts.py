# game-server/scripts/try_drafts.py

"""
장부 초안(app/drafts/)을 실제 언어 모델로 잰다. 서버도 DB 도 쓰지 않는다.

손으로 쓴 장면(evals/drafts/cases.py)마다 모델에게 장부 초안을 받고 정답과 견준다.
메시지의 조립, provider, 답 읽기, 서버의 검증은 서버와 같다(DraftWriter 를 그대로 쓴다).
기록장 자리에 목록을 꽂아, 답을 읽었는지(구조화 출력의 성공률)와 못 읽은 까닭을 기록에서 꺼낸다.

    uv run python -m scripts.try_drafts --model gemma4:26b-a4b-it-qat --repeat 10 --out $HOME\\drafts.md
    uv run python -m scripts.try_drafts --model gemma4:26b-a4b-it-qat qwen3:30b-a3b --case found lost

끝에 모델마다 센 표(읽음, 정답, 더한 것, 놓친 것, 지어낸 것)와 장면마다 맞힌 횟수를 찍는다.
"""

import argparse
import asyncio
import time
from pathlib import Path

import httpx

from app.ai.fake import FakeCallLog
from app.drafts.writer import DRAFT_PARAMS, DraftRequest, DraftWriter
from evals.drafts.cases import CASES, CONTEXT, DraftCase
from evals.drafts.scoring import DraftTrial, case_table, score, summarize, summary_table
from scripts.try_narration import make_provider, warm_up


def parse_arguments() -> argparse.Namespace:
    """명령줄을 읽는다."""
    parser = argparse.ArgumentParser(description='장부 초안을 실제 모델로 잰다')
    parser.add_argument('--model', required=True, nargs='+', help='모델 이름. 여럿을 띄어 적는다')
    parser.add_argument('--case', nargs='+', choices=[case.name for case in CASES], help='고른 장면만. 비우면 전부')
    parser.add_argument('--repeat', type=int, default=1, help='같은 모델, 같은 장면을 몇 번 돌릴까')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1', help='OpenAI 모양의 주소')
    parser.add_argument('--timeout', type=float, default=300.0, help='한 요청을 기다리는 시간(초)')
    parser.add_argument('--no-reasoning-field', action='store_true', help='추론 수준을 보내지 않는다')
    parser.add_argument('--no-warmup', action='store_true', help='모델을 미리 올리지 않는다')
    parser.add_argument('--out', type=Path, help='표와 답을 남길 파일(UTF-8)')
    return parser.parse_args()


def chosen_cases(names: list[str] | None) -> list[DraftCase]:
    """고른 장면들. 고르지 않았으면 전부다."""
    if not names:
        return list(CASES)
    return [case for case in CASES if case.name in names]


async def try_case(writer: DraftWriter, log: FakeCallLog, model: str, case: DraftCase) -> DraftTrial:
    """장면 하나를 한 번 돌린다. 기록장에 쌓인 마지막 기록에서 어떻게 끝났는지 꺼낸다."""
    started = time.perf_counter()
    checked = await writer.draft(DraftRequest(scene=case.scene, context=CONTEXT))
    seconds = time.perf_counter() - started
    record = log.records[-1]
    return score(model, case, seconds, checked, record.outcome, record.error, record.text)


def trial_line(trial: DraftTrial) -> str:
    """시도 하나를 한 줄로 찍는다."""
    mark = 'O' if trial.exact else ('?' if trial.read else 'X')
    found = sorted(trial.items) + sorted(trial.quests)
    return f'[{mark}] {trial.model} {trial.case} {trial.seconds:.1f}s {trial.error or ""} {found}'


async def run_model(client: httpx.AsyncClient, arguments: argparse.Namespace, model: str) -> list[DraftTrial]:
    """모델 하나로 고른 장면들을 repeat 번씩 돌린다."""
    provider = make_provider(client, arguments, model)
    if not arguments.no_warmup:
        await warm_up(provider)
    log = FakeCallLog()
    writer = DraftWriter(provider, log, params=DRAFT_PARAMS)
    trials = []
    for case in chosen_cases(arguments.case):
        for _ in range(arguments.repeat):
            trial = await try_case(writer, log, model, case)
            print(trial_line(trial), flush=True)
            trials.append(trial)
    return trials


async def run_all(arguments: argparse.Namespace) -> list[DraftTrial]:
    """모델마다 차례로 돌린다. 한 PC 의 GPU 하나라 동시에 돌리지 않는다."""
    trials = []
    async with httpx.AsyncClient() as client:
        for model in arguments.model:
            trials.extend(await run_model(client, arguments, model))
    return trials


def report(trials: list[DraftTrial]) -> str:
    """표 둘과, 정답이 아니었던 답들."""
    lines = [*summary_table(summarize(trials)), '', *case_table(trials), '', '## 정답이 아니었던 답', '']
    for trial in trials:
        if not trial.exact:
            lines.extend(
                [f'### {trial.model} / {trial.case} ({trial.error or "받음"})', '', trial.text or '(답 없음)', '']
            )
    return '\n'.join(lines)


def main() -> None:
    """명령줄을 읽고 돌리고 표를 찍는다. --out 이 있으면 파일에도 남긴다."""
    arguments = parse_arguments()
    trials = asyncio.run(run_all(arguments))
    text = report(trials)
    print(text)
    if arguments.out:
        arguments.out.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
