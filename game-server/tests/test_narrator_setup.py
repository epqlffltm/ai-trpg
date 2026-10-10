# game-server/tests/test_narrator_setup.py

"""
설정을 보고 서술자를 고르는 규칙(app/rounds/narrator_setup.py)과, 앱에 꽂히는 서술자를 검증한다.

모델을 부르지 않는다. 고르고 만드는 것만 본다.
"""

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.call_log import DbCallLog
from app.ai.openai_compat import OpenAICompatProvider
from app.main import create_app
from app.rounds.llm_narrator import LLMNarrator
from app.rounds.narrator import FakeNarrator
from app.rounds.narrator_setup import build_narrator, build_provider
from app.rounds.retrying_narrator import RetryingNarrator
from tests.conftest import make_test_settings

LLM = {'narrator': 'llm', 'llm_model': 'gemma4:26b'}


def test_the_fake_narrator_is_chosen_by_default():
    narrator = build_narrator(make_test_settings(), httpx.AsyncClient(), async_sessionmaker())

    assert isinstance(narrator, FakeNarrator)


def test_the_language_model_narrator_retries_one_model_by_default():
    narrator = build_narrator(make_test_settings(**LLM), httpx.AsyncClient(), async_sessionmaker())

    # 넘어갈 모델을 적지 않으면 첫 모델 하나를 다시 시도하는 서술자다
    assert isinstance(narrator, RetryingNarrator)
    (inner,) = narrator.narrators
    assert isinstance(inner, LLMNarrator)
    assert isinstance(inner.provider, OpenAICompatProvider)
    assert (inner.provider.kind, inner.provider.model) == ('openai_compat', 'gemma4:26b')


def test_the_fallback_models_follow_the_first_in_order():
    settings = make_test_settings(**LLM, llm_fallback_models=' gemma4:31b-it-qat, ,qwen3.6:27b ')

    narrator = build_narrator(settings, httpx.AsyncClient(), async_sessionmaker())

    # 빈 이름과 앞뒤 공백은 뺀다. 적은 차례대로 넘어간다
    assert [inner.provider.model for inner in narrator.narrators] == ['gemma4:26b', 'gemma4:31b-it-qat', 'qwen3.6:27b']


def test_one_call_may_take_as_long_as_the_timeout():
    narrator = build_narrator(
        make_test_settings(**LLM, llm_timeout_seconds=45), httpx.AsyncClient(), async_sessionmaker()
    )

    # 남은 시간을 셀 때 쓴다. 남은 시간이 이보다 짧으면 새로 부르지 않는다
    assert narrator.attempt_timeout == 45


def test_the_provider_takes_its_values_from_the_settings():
    client = httpx.AsyncClient()
    settings = make_test_settings(
        **LLM, llm_base_url='http://127.0.0.1:1234/v1', llm_timeout_seconds=30, llm_supports_reasoning=False
    )

    provider = build_provider(settings, client, 'gemma4:31b-it-qat')

    assert provider.client is client
    assert provider.base_url == 'http://127.0.0.1:1234/v1'
    assert provider.model == 'gemma4:31b-it-qat'
    assert provider.timeout == 30
    assert provider.supports_reasoning is False


def test_tests_use_the_fake_narrator_whatever_the_env_file_says(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('NARRATOR', 'llm')
    monkeypatch.setenv('LLM_MODEL', 'gemma4:26b')

    # 개발자가 .env 에 언어 모델을 켜 두어도 테스트는 실제 모델을 부르지 않는다
    assert make_test_settings().narrator == 'fake'


def test_the_app_plugs_in_the_chosen_narrator():
    fake = create_app(make_test_settings())
    llm = create_app(make_test_settings(**LLM))

    assert isinstance(fake.state.narrator, FakeNarrator)
    assert isinstance(llm.state.narrator, RetryingNarrator)


def test_every_model_is_called_with_the_client_the_app_closes():
    app = create_app(make_test_settings(**LLM, llm_fallback_models='gemma4:31b-it-qat'))

    # 앱이 꺼질 때 이 클라이언트를 닫는다(lifespan). 따로 만든 클라이언트면 닫히지 않고 남는다
    for inner in app.state.narrator.narrators:
        assert inner.provider.client is app.state.http_client


def test_every_model_call_is_recorded_in_the_database_of_the_app():
    app = create_app(make_test_settings(**LLM, llm_fallback_models='gemma4:31b-it-qat'))

    # 기록 없이 모델을 부르는 길이 없다. 넘어간 모델의 호출도 앱의 세션 틀로 ai_invocations 에 쓴다
    for inner in app.state.narrator.narrators:
        assert isinstance(inner.log, DbCallLog)
        assert inner.log.session_factory is app.state.session_factory
