# game-server/scripts/eval_memory.py

"""
지난 일(앞 라운드의 기억) 검색을 평가한다(#107).
정답을 붙인 질의(evals/memory/chase_log.yaml)로 서버의 고르는 규칙을 잰다.

서버도 DB 도 쓰지 않는다. 임베딩 모델만 부른다. 기억을 만드는 법과 고르는 규칙은 서버의 것과 같다.
거리 기준을 바꿔 가며 점수를 매겨,
서버의 거리 기준(MEMORY_MAX_DISTANCE, MEMORY_KEYWORD_MAX_DISTANCE)을 정할 근거를 만든다.
임베딩 모델을 바꾸면 이것으로 다시 재서 설정을 고친다.

    uv run python -m scripts.eval_memory
    uv run python -m scripts.eval_memory --model bge-m3 --out $HOME\\memory-eval.md
    uv run python -m scripts.eval_memory --fake

game-server 폴더에서 -m 으로 돌린다. 임베딩 주소는 설정(.env)의 것을 쓴다(EMBEDDING_BASE_URL, 비면 LLM_BASE_URL).
--fake 는 모델 없이 가짜 임베더로 돈다. 낱말이 겹치는지만 보는 가짜라 숫자에 뜻은 없다. 스크립트가 도는지 볼 때 쓴다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from app.ai.embedder import Embedder
from app.ai.provider import ProviderError
from app.core.config import get_settings
from app.memory.retrieval import MemoryThresholds
from evals.lore.dataset import DatasetError
from evals.memory.dataset import DEFAULT_PATH, MemoryDataset, load_dataset
from evals.memory.report import ModelResult, full_report
from evals.memory.runner import evaluate, measure, sweep
from scripts.eval_lore import make_embedders


def read_arguments() -> argparse.Namespace:
    """명령줄의 값을 읽는다."""
    parser = argparse.ArgumentParser(description='지난 일 검색을 평가한다.')
    parser.add_argument('--model', nargs='+', help='임베딩 모델. 여럿을 띄어 적는다. 없으면 설정의 것')
    parser.add_argument('--data', type=Path, default=DEFAULT_PATH, help='평가 데이터(YAML)')
    parser.add_argument('--base-url', help='임베딩 주소. 적지 않으면 설정의 것')
    parser.add_argument('--fake', action='store_true', help='모델 없이 가짜 임베더로 돌린다(숫자에 뜻은 없다)')
    parser.add_argument('--out', type=Path, help='보고서를 남길 파일(UTF-8)')
    return parser.parse_args()


def current_thresholds() -> MemoryThresholds:
    """지금 서버의 기준. 설정의 값이다."""
    settings = get_settings()
    return MemoryThresholds(settings.memory_max_distance, settings.memory_keyword_max_distance)


async def evaluate_model(embedder: Embedder, dataset: MemoryDataset, thresholds: MemoryThresholds) -> ModelResult:
    """모델 하나를 재고, 지금의 기준과 여러 기준으로 점수를 매긴다."""
    measurement = await measure(embedder, dataset)
    return ModelResult(measurement, evaluate(dataset, measurement, thresholds), sweep(dataset, measurement))


async def run(arguments: argparse.Namespace) -> str:
    """데이터를 읽고 모델마다 평가해 보고서를 만든다."""
    dataset = load_dataset(arguments.data)
    thresholds = current_thresholds()
    async with httpx.AsyncClient() as client:
        results = [
            await evaluate_model(embedder, dataset, thresholds) for embedder in make_embedders(arguments, client)
        ]
    return full_report(dataset, results)


def failure_message(error: Exception) -> str:
    """실패를 사람이 읽을 한 줄로. 모델의 응답 내용은 담지 않는다(ProviderError 는 이유의 이름만 가진다)."""
    if isinstance(error, DatasetError):
        return f'평가 데이터가 틀렸다.\n{error}'
    return f'임베딩 모델을 부르지 못했다: {error}. 모델 이름과 주소, 모델이 받아져 있는지 확인한다'


def main() -> None:
    """명령줄을 읽고, 돌리고, 보고서를 찍고, 원하면 파일로 남긴다. 알려진 실패는 한 줄로 알리고 1 로 끝난다."""
    arguments = read_arguments()
    try:
        report = asyncio.run(run(arguments))
    except (DatasetError, ProviderError) as error:
        print(failure_message(error), file=sys.stderr)
        sys.exit(1)
    print(report)
    if arguments.out is not None:
        arguments.out.write_text(report, encoding='utf-8')
        print(f'\n저장했다: {arguments.out}')


if __name__ == '__main__':
    main()
