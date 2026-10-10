# game-server/scripts/eval_lore.py

"""
로어북 검색을 평가한다(#93 ③). 정답을 붙인 질의(evals/lore/chase.yaml)로 키워드, 벡터, 둘을 합친 것을 견준다.

서버도 DB 도 쓰지 않는다. 임베딩 모델만 부른다. 거리 계산과 고르는 규칙은 서버의 것과 같다(evals/lore/metrics.py).
거리 기준을 바꿔 가며 점수를 매겨, 서버의 MAX_DISTANCE 를 정할 근거를 만든다.
키워드로 걸린 항목에도 거리 상한을 두는 방식 둘(질의 기준, 문장 기준)을 함께 잰다. 동음이의어를 막을 후보다.

    uv run python -m scripts.eval_lore
    uv run python -m scripts.eval_lore --model bge-m3 qwen3-embedding:0.6b --out $HOME\\lore-eval.md
    uv run python -m scripts.eval_lore --set v1
    uv run python -m scripts.eval_lore --fake

game-server 폴더에서 -m 으로 돌린다. 임베딩 주소는 설정(.env)의 것을 쓴다(EMBEDDING_BASE_URL, 비면 LLM_BASE_URL).
--fake 는 모델 없이 가짜 임베더로 돈다. 낱말이 겹치는지만 보는 가짜라 숫자에 뜻은 없다. 스크립트가 도는지 볼 때 쓴다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from app.ai.embedder import Embedder
from app.ai.fake import FakeEmbedder
from app.ai.openai_embedder import OpenAICompatEmbedder
from app.ai.provider import ProviderError
from app.core.config import get_settings
from evals.lore.dataset import DEFAULT_PATH, Dataset, DatasetError, load_dataset, only_set
from evals.lore.report import ModelResult, best, full_report
from evals.lore.runner import evaluate, measure, sweep, sweep_gates


def read_arguments() -> argparse.Namespace:
    """명령줄의 값을 읽는다."""
    parser = argparse.ArgumentParser(description='로어북 검색을 평가한다.')
    parser.add_argument('--model', nargs='+', help='임베딩 모델. 여럿을 띄어 적는다. 없으면 설정의 것')
    parser.add_argument('--set', help='이 묶음의 질의만 돌린다(v1 …). 적지 않으면 전부')
    parser.add_argument('--data', type=Path, default=DEFAULT_PATH, help='평가 데이터(YAML)')
    parser.add_argument('--base-url', help='임베딩 주소. 적지 않으면 설정의 것')
    parser.add_argument('--fake', action='store_true', help='모델 없이 가짜 임베더로 돌린다(숫자에 뜻은 없다)')
    parser.add_argument('--out', type=Path, help='보고서를 남길 파일(UTF-8)')
    return parser.parse_args()


def make_embedders(arguments: argparse.Namespace, client: httpx.AsyncClient) -> list[Embedder]:
    """평가할 임베더들. --fake 면 가짜 하나다."""
    if arguments.fake:
        return [FakeEmbedder()]
    settings = get_settings()
    base_url = arguments.base_url or settings.embedding_url()
    models = arguments.model or [settings.embedding_model]
    return [
        OpenAICompatEmbedder(
            client=client, base_url=base_url, model=model.strip(), timeout=settings.embedding_timeout_seconds
        )
        for model in models
    ]


async def evaluate_model(embedder: Embedder, dataset: Dataset) -> ModelResult:
    """
    모델 하나를 재고 점수를 매긴다. 지금의 거리 기준, 여러 거리 기준,
    그리고 가장 나은 거리 기준에서 키워드의 상한을 바꿔 가며.
    """
    measurement = await measure(embedder, dataset)
    swept = sweep(dataset, measurement)
    gated = sweep_gates(dataset, measurement, best(swept).max_distance)
    return ModelResult(measurement, evaluate(dataset, measurement), swept, gated)


class NoQueries(Exception):
    """돌릴 질의가 없다(--set 의 이름이 틀렸을 때)."""


def read_dataset(arguments: argparse.Namespace) -> Dataset:
    """데이터를 읽고 묶음을 고른다. 질의가 하나도 남지 않으면 NoQueries."""
    dataset = only_set(load_dataset(arguments.data), arguments.set)
    if not dataset.queries:
        raise NoQueries(arguments.set)
    return dataset


async def run(arguments: argparse.Namespace) -> str:
    """데이터를 읽고 모델마다 평가해 보고서를 만든다."""
    dataset = read_dataset(arguments)
    async with httpx.AsyncClient() as client:
        results = [await evaluate_model(embedder, dataset) for embedder in make_embedders(arguments, client)]
    return full_report(dataset, results)


def failure_message(error: Exception) -> str:
    """실패를 사람이 읽을 한 줄로. 모델의 응답 내용은 담지 않는다(ProviderError 는 이유의 이름만 가진다)."""
    if isinstance(error, DatasetError):
        return f'평가 데이터가 틀렸다.\n{error}'
    if isinstance(error, NoQueries):
        return f'그 묶음의 질의가 없다: {error}'
    return f'임베딩 모델을 부르지 못했다: {error}. 모델 이름과 주소, 모델이 받아져 있는지 확인한다'


def main() -> None:
    """명령줄을 읽고, 돌리고, 보고서를 찍고, 원하면 파일로 남긴다. 알려진 실패는 한 줄로 알리고 1 로 끝난다."""
    arguments = read_arguments()
    try:
        report = asyncio.run(run(arguments))
    except (DatasetError, NoQueries, ProviderError) as error:
        print(failure_message(error), file=sys.stderr)
        sys.exit(1)
    print(report)
    if arguments.out is not None:
        arguments.out.write_text(report, encoding='utf-8')
        print(f'\n저장했다: {arguments.out}')


if __name__ == '__main__':
    main()
