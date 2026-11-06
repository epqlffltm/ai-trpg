# chat-server/scripts/try_prefill.py

"""
이어서 출력(#675)에 공급자의 "답 미리 채우기"를 쓸 수 있는지 실제 모델로 재 보는 연구·개발용 명령.

    uv run python -m scripts.try_prefill claude-opus-5-5 gpt-6-luna gemma4:26b
    uv run python -m scripts.try_prefill claude-opus-5-5 --out prefill.md

chat-server 폴더에서 -m 으로 돌린다. 키와 창구의 주소는 이 서버의 설정(.env)에서 읽는다(OPENAI_API_KEY 등).
DB 를 쓰지 않는다. 모델은 ai-core 에 든 모델 목록(model_catalog.toml)에서 찾고, 꺼진 모델도 부른다.
목록에 없는 이름은 서버 곁의 모델(LLM_BASE_URL)로 부른다. 모델마다 두 번 부른다(값이 든다).

  - 미리 채우기(prefill): 대화의 끝을 끊긴 답(모델 쪽의 말)으로 보낸다. 받는 공급자는 그 뒤를 이어 쓴다
  - 지시(instruction): 지금 쓰는 길. 끊긴 답 뒤에 "이어 써라"는 지시를 사람의 차례로 붙인다
    (conversation_core/continuation.py 의 instruction)

모델마다 두 길의 결과(실패의 까닭, 걸린 시간, 되풀이한 앞부분의 길이, 받은 글)를 찍는다.
이어 썼는지, 말투가 이어지는지는 사람이 글을 읽고 정한다. --out 을 주면 같은 것을 마크다운 파일로도 적는다.
운영 서버는 이 명령을 쓰지 않는다.
"""

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from ai_core.catalog_contract import CatalogModel
from ai_core.catalog_file import ModelEntry, load_catalog
from ai_core.provider import ChatMessage, GenerationParams, LLMProvider, ProviderError, Role
from ai_core.routing import (
    ANTHROPIC_KIND,
    DEEPINFRA_KIND,
    GEMINI_KIND,
    LOCAL_KIND,
    OPENAI_KIND,
    ZAI_KIND,
    Endpoint,
    ModelRouter,
)
from conversation_core.continuation import instruction, repeated_length

from app.core.config import Settings, get_settings
from app.turns.providers import endpoint

# 재는 대화. 캐릭터의 답이 문장 가운데서 끊겼다
SYSTEM = '너는 이야기 속 인물 "세라"다. 세라의 말과 행동만 한국어로 쓴다. 해설이나 사용자의 말은 쓰지 않는다.'
ASKED = '세라, 어젯밤 시계탑에서 무엇을 봤는지 자세히 말해 줘.'
PARTIAL = '세라가 찻잔을 내려놓고 창밖을 본다. "자정이 조금 지났을 때였어. 시계탑 꼭대기에서 푸른 불빛이'
# 이어 쓴 글의 길이. 판단에 충분할 만큼만 받는다
PARAMS = GenerationParams(max_tokens=200, temperature=0.7)
# 찍는 글의 앞부분(글자)
SHOWN_CHARS = 160

PREFILL = 'prefill'
INSTRUCTION = 'instruction'


@dataclass(frozen=True)
class Probe:
    """한 길의 결과. 실패했으면 error 가 까닭이고 text 는 비어 있다."""

    way: str
    seconds: float
    text: str = ''
    error: str | None = None
    finish_reason: str | None = None

    @property
    def repeated(self) -> int:
        """받은 글의 앞이 끊긴 답의 끝과 겹친 길이(글자). 겹침이 짧으면 0."""
        return repeated_length(PARTIAL, self.text) if self.text else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """명령줄을 읽는다."""
    parser = argparse.ArgumentParser(description='이어서 출력에 미리 채우기를 쓸 수 있는지 실제 모델로 잰다(#675).')
    parser.add_argument('models', nargs='+', help='모델 목록의 이름표, 또는 서버 곁의 모델 이름')
    parser.add_argument('--out', type=Path, help='결과를 적을 마크다운 파일')
    return parser.parse_args(argv)


def prefill_messages() -> list[ChatMessage]:
    """미리 채우기: 대화의 끝이 끊긴 답이다."""
    return [
        ChatMessage(Role.SYSTEM, SYSTEM),
        ChatMessage(Role.USER, ASKED),
        ChatMessage(Role.ASSISTANT, PARTIAL),
    ]


def instruction_messages() -> list[ChatMessage]:
    """지시: 끊긴 답 뒤에 이어 쓰라는 지시를 사람의 차례로 붙인다(지금의 이어서 출력)."""
    return [*prefill_messages(), ChatMessage(Role.USER, instruction())]


def to_catalog_model(entry: ModelEntry) -> CatalogModel:
    """파일의 모델 하나를 부를 때의 값으로. 켜고 끄기와 은퇴일은 보지 않는다(재는 명령이다)."""
    return CatalogModel(
        slug=entry.slug,
        provider=entry.provider,
        api_model_id=entry.api_model_id,
        supports_reasoning=entry.supports_reasoning,
        supports_temperature=entry.supports_temperature,
        token_limit_field=entry.token_limit_field,
        enabled=True,
        retires_on=None,
        reasoning_style=entry.reasoning_style,
    )


@dataclass(frozen=True)
class FileLookup:
    """모델 목록 파일에서 찾는다. DB 를 쓰지 않는다."""

    models: dict[str, CatalogModel]

    async def find(self, slug: str, day: date) -> CatalogModel | None:
        """그 이름표의 모델. 목록에 없으면 None(서버 곁의 모델로 부른다)."""
        return self.models.get(slug)


def file_lookup() -> FileLookup:
    """설치된 ai-core 에 든 모델 목록."""
    return FileLookup({entry.slug: to_catalog_model(entry) for entry in load_catalog().models})


def build_router(settings: Settings, client: httpx.AsyncClient) -> ModelRouter:
    """설정의 키로 창구들을 만든다. 키가 없는 창구의 모델은 provider_not_configured 로 실패한다."""
    return ModelRouter(
        lookup=file_lookup(),
        client=client,
        local=Endpoint(base_url=settings.llm_base_url, api_key=None, kind=LOCAL_KIND),
        openai=endpoint(settings.openai_base_url, settings.openai_api_key, OPENAI_KIND),
        anthropic=endpoint(settings.anthropic_base_url, settings.anthropic_api_key, ANTHROPIC_KIND),
        gemini=endpoint(settings.gemini_base_url, settings.gemini_api_key, GEMINI_KIND),
        zai=endpoint(settings.zai_base_url, settings.zai_api_key, ZAI_KIND),
        deepinfra=endpoint(settings.deepinfra_base_url, settings.deepinfra_api_key, DEEPINFRA_KIND),
        timeout=settings.llm_timeout_seconds,
    )


async def probe(provider: LLMProvider, way: str, messages: list[ChatMessage]) -> Probe:
    """한 길로 한 번 부른다. 실패해도 올리지 않고 까닭을 담는다."""
    started = time.monotonic()
    try:
        completion = await provider.complete(messages, PARAMS)
    except ProviderError as error:
        return Probe(way=way, seconds=time.monotonic() - started, error=str(error))
    return Probe(
        way=way, seconds=time.monotonic() - started, text=completion.text, finish_reason=completion.finish_reason
    )


async def probe_model(router: ModelRouter, name: str) -> tuple[Probe, ...]:
    """모델 하나를 두 길로 잰다. 모델을 부를 수 없으면 두 길 모두 그 까닭이다."""
    try:
        provider = await router.provider_for(name, allow_disabled=True)
    except ProviderError as error:
        return (Probe(PREFILL, 0.0, error=str(error)), Probe(INSTRUCTION, 0.0, error=str(error)))
    return (
        await probe(provider, PREFILL, prefill_messages()),
        await probe(provider, INSTRUCTION, instruction_messages()),
    )


def one_line(text: str) -> str:
    """찍을 글. 줄바꿈과 표의 칸 구분을 바꾸고 앞부분만."""
    flat = text.replace('\n', ' ⏎ ').replace('|', '\\|')
    return flat if len(flat) <= SHOWN_CHARS else f'{flat[:SHOWN_CHARS]}…'


def row(name: str, result: Probe) -> str:
    """표의 한 줄."""
    if result.error is not None:
        return f'| {name} | {result.way} | 실패: {result.error} | {result.seconds:.1f} | - | |'
    return (
        f'| {name} | {result.way} | {result.finish_reason or "-"} | {result.seconds:.1f} | {result.repeated} '
        f'| {one_line(result.text)} |'
    )


def report(results: dict[str, tuple[Probe, ...]]) -> str:
    """결과 전부. 재는 대화와 표."""
    lines = [
        '# 이어서 출력: 미리 채우기와 지시(#675)',
        '',
        f'- 묻는 말: {ASKED}',
        f'- 끊긴 답: {PARTIAL}',
        '- 되풀이: 받은 글의 앞이 끊긴 답의 끝과 겹친 글자 수(8글자보다 짧으면 0)',
        '',
        '| 모델 | 길 | 멈춘 까닭 | 초 | 되풀이 | 받은 글 |',
        '| --- | --- | --- | ---: | ---: | --- |',
    ]
    lines += [row(name, result) for name, probes in results.items() for result in probes]
    return '\n'.join(lines) + '\n'


async def run(args: argparse.Namespace) -> int:
    """모델마다 두 길로 재고 찍는다."""
    settings = get_settings()
    results: dict[str, tuple[Probe, ...]] = {}
    async with httpx.AsyncClient() as client:
        router = build_router(settings, client)
        for name in args.models:
            results[name] = await probe_model(router, name)
    text = report(results)
    print(text)
    if args.out:
        args.out.write_text(text, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(run(parse_args(sys.argv[1:]))))
