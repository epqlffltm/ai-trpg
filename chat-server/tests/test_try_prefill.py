# chat-server/tests/test_try_prefill.py

"""
이어서 출력의 미리 채우기를 재는 명령(scripts/try_prefill.py, #675)을 검증한다. 실제 모델은 부르지 않는다.

보는 것.
  - 두 길의 대화: 미리 채우기는 끊긴 답(모델의 말)으로 끝나고, 지시는 그 뒤에 이어 쓰라는 지시(사람의 말)가 붙는다
  - 모델 목록 파일의 모델을 찾고, 꺼졌거나 은퇴한 모델도 부를 수 있는 값으로 바꾼다
  - 부를 수 없는 모델(키가 없다)은 두 길 모두 그 까닭이다. 부르다 실패하면 그 길에 까닭을 담는다
  - 되풀이한 앞부분의 길이를 재고, 표의 한 줄에 줄바꿈과 칸 구분을 바꾸어 싣는다
"""

from dataclasses import dataclass, field

import httpx
import pytest
from ai_core.catalog_contract import Provider
from ai_core.catalog_file import load_catalog
from ai_core.fake import FakeProvider
from ai_core.provider import ChatMessage, Completion, GenerationParams, ProviderError, Role
from ai_core.routing import Endpoint, ModelRouter
from conversation_core.continuation import instruction

from scripts import try_prefill
from scripts.try_prefill import INSTRUCTION, PARTIAL, PREFILL, Probe


@dataclass
class BrokenProvider:
    """미리 채우기를 받지 않는 공급자처럼 실패한다."""

    reason: str = 'status_400'
    kind: str = 'fake'
    model: str = 'broken'
    calls: list[list[ChatMessage]] = field(default_factory=list)

    async def complete(self, messages: list[ChatMessage], params: GenerationParams, on_text=None) -> Completion:
        self.calls.append(list(messages))
        raise ProviderError(self.reason)


def test_the_prefill_ends_with_the_broken_answer_and_the_instruction_follows_it():
    prefill = try_prefill.prefill_messages()
    told = try_prefill.instruction_messages()

    assert [message.role for message in prefill] == [Role.SYSTEM, Role.USER, Role.ASSISTANT]
    assert prefill[-1].content == PARTIAL
    assert told[:-1] == prefill
    assert told[-1] == ChatMessage(Role.USER, instruction())


def test_the_bundled_catalog_is_looked_up_with_every_model_callable():
    lookup = try_prefill.file_lookup()
    entry = load_catalog().models[0]

    model = lookup.models[entry.slug]

    assert (model.api_model_id, model.enabled, model.retires_on) == (entry.api_model_id, True, None)


async def test_a_model_without_a_key_fails_both_ways():
    anthropic = next(entry for entry in load_catalog().models if entry.provider == Provider.ANTHROPIC)
    async with httpx.AsyncClient() as client:
        router = ModelRouter(
            lookup=try_prefill.file_lookup(),
            client=client,
            local=Endpoint(base_url='http://127.0.0.1:1/v1', api_key=None, kind='openai_compat'),
            openai=None,
            timeout=1.0,
        )
        probes = await try_prefill.probe_model(router, anthropic.slug)

    assert [(result.way, result.error) for result in probes] == [
        (PREFILL, 'provider_not_configured'),
        (INSTRUCTION, 'provider_not_configured'),
    ]


async def test_a_refused_prefill_keeps_its_reason():
    broken = BrokenProvider()

    result = await try_prefill.probe(broken, PREFILL, try_prefill.prefill_messages())

    assert (result.way, result.error, result.text) == (PREFILL, 'status_400', '')
    assert broken.calls[0][-1].role == Role.ASSISTANT


async def test_a_repeated_start_is_measured():
    repeating = FakeProvider(reply='시계탑 꼭대기에서 푸른 불빛이 깜박였어."')

    result = await try_prefill.probe(repeating, INSTRUCTION, try_prefill.instruction_messages())
    fresh = Probe(PREFILL, 0.5, text=' 깜박였어."')

    assert result.repeated == len('시계탑 꼭대기에서 푸른 불빛이')
    assert fresh.repeated == 0


def test_the_report_puts_one_way_on_each_line():
    results = {
        'claude-x': (
            Probe(PREFILL, 1.25, text='깜박였어.\n"그게 다야|정말"', finish_reason='end_turn'),
            Probe(INSTRUCTION, 0.0, error='status_400'),
        )
    }

    text = try_prefill.report(results)

    assert '| claude-x | prefill | end_turn | 1.2 | 0 | 깜박였어. ⏎ "그게 다야\\|정말" |' in text
    assert '| claude-x | instruction | 실패: status_400 | 0.0 | - | |' in text


@pytest.mark.parametrize('argv', [['gpt-6-luna'], ['a', 'b', '--out', 'x.md']])
def test_the_arguments_are_read(argv: list[str]):
    args = try_prefill.parse_args(argv)

    assert args.models == [name for name in argv if name not in ('--out', 'x.md')]
