# trpg-server/scripts/eval_references.py

"""
참고 자료(#482)를 평가한다. 서버도 DB 도 쓰지 않는다.

둘을 잰다.
  1. 검색: 한국어 장면(evals/references/scenes.yaml)에서 영어 SRD(data/references/srd51.json)를 얼마나 맞게 고르는가.
     임베딩 모델만 부른다. 거리 기준을 바꿔 가며 점수를 매겨 REFERENCE_MAX_DISTANCE 를 정할 근거를 만든다.
  2. 서술(--narrate): 같은 장면을 참고 자료를 끈 것과 켠 것으로 서술하게 해 견준다.
     늘어난 입력 토큰, 수치가 샌 서술, 길이를 세고 장면을 보고서에 남긴다. 나아졌는지는 사람이 읽고 판단한다.

    uv run python -m scripts.eval_references
    uv run python -m scripts.eval_references --model bge-m3 qwen3-embedding:0.6b --out $HOME\\refs-eval.md
    uv run python -m scripts.eval_references --narrate --narration-model gemma4:26b-a4b-it-qat --repeat 2
    uv run python -m scripts.eval_references --narrate --max-distance 0.55
    uv run python -m scripts.eval_references --fake --narrate

trpg-server 폴더에서 -m 으로 돌린다. 임베딩 주소는 설정(.env)의 것(EMBEDDING_BASE_URL, 비면 LLM_BASE_URL)이다.
서술 모델의 주소는 --base-url(기본 집의 Ollama)이다.
--fake 는 모델 없이 가짜 임베더와 정해 둔 글로 돈다. 숫자에 뜻은 없다. 스크립트가 끝까지 도는지 볼 때 쓴다.
서술은 첫째 임베딩 모델로 고른 참고 자료를 쓴다. 자동 테스트가 아니라서 CI 에서 돌지 않는다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from app.ai.embedder import Embedder
from app.ai.fake import FakeEmbedder, FakeProvider
from app.ai.openai_embedder import OpenAICompatEmbedder
from app.ai.provider import LLMProvider, ProviderError
from app.core.config import get_settings
from app.references.retrieval import ReferenceThresholds
from evals.references.dataset import DEFAULT_SCENES, Dataset, DatasetError, chosen_sets, load_dataset
from evals.references.narration import Trial, run_pairs
from evals.references.report import ModelResult, full_report
from evals.references.runner import evaluate, measure, sweep
from scripts.try_narration import make_provider, warm_up

# 기본 서술 모델. 서버의 기본 서술 모델과 같다
DEFAULT_NARRATION_MODEL = 'gemma4:26b-a4b-it-qat'
# --fake 의 서술. 수치를 흘린다. 검사가 걸리는 것을 본다
FAKE_SCENE = '엘프가 횃불을 높이 든다. 불빛이 동굴 벽을 핥는다. 횃불은 한 시간쯤 탄다. DC 12 의 판정이 떠오른다.'


def read_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """명령줄의 값을 읽는다."""
    parser = argparse.ArgumentParser(description='참고 자료의 검색과 서술을 평가한다.')
    parser.add_argument('--model', nargs='+', help='임베딩 모델. 여럿을 띄어 적는다. 없으면 설정의 것')
    parser.add_argument('--set', nargs='+', help='이 묶음의 장면만 돌린다(v1 …). 적지 않으면 전부')
    parser.add_argument('--scenes', type=Path, default=DEFAULT_SCENES, help='장면 파일(YAML)')
    parser.add_argument('--embedding-url', help='임베딩 주소. 적지 않으면 설정의 것')
    parser.add_argument('--max-distance', type=float, help='거리 기준. 적지 않으면 설정의 REFERENCE_MAX_DISTANCE')
    parser.add_argument('--narrate', action='store_true', help='켠 서술과 끈 서술을 견준다')
    parser.add_argument('--narration-model', default=DEFAULT_NARRATION_MODEL, help='서술 모델')
    parser.add_argument('--repeat', type=int, default=1, help='장면마다 몇 번씩 서술하게 할까')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1', help='서술 모델의 OpenAI 모양 주소')
    parser.add_argument('--timeout', type=float, default=300.0, help='서술 요청 하나를 기다리는 시간(초)')
    parser.add_argument('--no-reasoning-field', action='store_true', help='추론 수준을 보내지 않는다')
    parser.add_argument('--fake', action='store_true', help='모델 없이 가짜로 돈다(숫자에 뜻은 없다)')
    parser.add_argument('--out', type=Path, help='보고서를 남길 파일(UTF-8)')
    return parser.parse_args(argv)


def thresholds_of(arguments: argparse.Namespace) -> ReferenceThresholds:
    """고르는 규칙. 거리 기준은 명령줄, 없으면 설정의 것이다. --fake 면 설정을 읽지 않고 기본값이다."""
    if arguments.fake:
        return ReferenceThresholds() if arguments.max_distance is None else ReferenceThresholds(arguments.max_distance)
    settings = get_settings()
    distance = arguments.max_distance or settings.reference_max_distance
    return ReferenceThresholds(distance, settings.reference_keyword_max_distance)


def make_embedders(arguments: argparse.Namespace, client: httpx.AsyncClient) -> list[Embedder]:
    """평가할 임베더들. --fake 면 가짜 하나다."""
    if arguments.fake:
        return [FakeEmbedder()]
    settings = get_settings()
    base_url = arguments.embedding_url or settings.embedding_url()
    models = arguments.model or [settings.embedding_model]
    return [
        OpenAICompatEmbedder(
            client=client, base_url=base_url, model=model.strip(), timeout=settings.embedding_timeout_seconds
        )
        for model in models
    ]


async def narration_provider(arguments: argparse.Namespace, client: httpx.AsyncClient) -> LLMProvider:
    """서술 모델. --fake 면 정해 둔 글을 돌려주는 가짜다. 아니면 메모리에 올려 둔다."""
    if arguments.fake:
        return FakeProvider(reply=FAKE_SCENE)
    provider = make_provider(client, arguments, arguments.narration_model)
    await warm_up(provider)
    return provider


def print_trial(trial: Trial) -> None:
    """서술 하나가 끝날 때마다 찍는다."""
    state = '실패' if trial.text is None else f'{len(trial.text)}자'
    print(f'{trial.scene_name} {trial.mode} {trial.attempt}회: {state}', flush=True)


class NoScenes(Exception):
    """돌릴 장면이 없다(--set 의 이름이 틀렸을 때)."""


def read_dataset(arguments: argparse.Namespace) -> Dataset:
    """데이터를 읽고 묶음을 고른다. 장면이 하나도 남지 않으면 NoScenes."""
    dataset = chosen_sets(load_dataset(arguments.scenes), arguments.set)
    if not dataset.scenes:
        raise NoScenes(arguments.set)
    return dataset


async def run(arguments: argparse.Namespace) -> str:
    """데이터를 읽고 임베딩 모델마다 재고, 원하면 서술을 견줘 보고서를 만든다."""
    dataset = read_dataset(arguments)
    thresholds = thresholds_of(arguments)
    results: list[ModelResult] = []
    trials: list[Trial] = []
    async with httpx.AsyncClient() as client:
        for embedder in make_embedders(arguments, client):
            measurement = await measure(embedder, dataset)
            current = evaluate(dataset, measurement, thresholds)
            results.append(ModelResult(measurement, current, sweep(dataset, measurement, thresholds)))
        if arguments.narrate:
            provider = await narration_provider(arguments, client)
            measured = results[0].measurement
            trials = await run_pairs(provider, dataset, measured, thresholds, arguments.repeat, print_trial)
    return full_report(dataset, results, thresholds, trials)


def failure_message(error: Exception) -> str:
    """실패를 사람이 읽을 한 줄로."""
    if isinstance(error, DatasetError):
        return f'평가 데이터가 틀렸다.\n{error}'
    if isinstance(error, NoScenes):
        return f'그 묶음의 장면이 없다: {error}'
    return f'임베딩 모델을 부르지 못했다: {error}. 모델 이름과 주소, 모델이 받아져 있는지 확인한다'


def main(argv: list[str] | None = None) -> int:
    """명령줄을 읽고, 돌리고, 보고서를 찍고, 원하면 파일로 남긴다. 알려진 실패는 한 줄로 알리고 1 을 돌려준다."""
    arguments = read_arguments(argv)
    try:
        report = asyncio.run(run(arguments))
    except (DatasetError, NoScenes, ProviderError) as error:
        print(failure_message(error), file=sys.stderr)
        return 1
    print(report)
    if arguments.out is not None:
        arguments.out.write_text(report, encoding='utf-8')
        print(f'\n저장했다: {arguments.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
