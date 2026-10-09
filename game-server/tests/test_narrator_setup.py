# game-server/tests/test_narrator_setup.py

"""
설정을 보고 서술자를 고르는 규칙(app/rounds/narrator_setup.py)과, 앱에 꽂히는 서술자를 검증한다.

모델을 부르지 않는다. 고르고 만드는 것만 본다.
"""

import httpx
import pytest

from app.ai.openai_compat import OpenAICompatProvider
from app.main import create_app
from app.rounds.llm_narrator import LLMNarrator
from app.rounds.narrator import FakeNarrator
from app.rounds.narrator_setup import build_narrator, build_provider
from tests.conftest import make_test_settings

LLM = {'narrator': 'llm', 'llm_model': 'gemma4:26b'}


def test_the_fake_narrator_is_chosen_by_default():
    narrator = build_narrator(make_test_settings(), httpx.AsyncClient())

    assert isinstance(narrator, FakeNarrator)


def test_the_language_model_narrator_is_chosen_when_asked():
    narrator = build_narrator(make_test_settings(**LLM), httpx.AsyncClient())

    assert isinstance(narrator, LLMNarrator)
    assert isinstance(narrator.provider, OpenAICompatProvider)


def test_the_provider_takes_its_values_from_the_settings():
    client = httpx.AsyncClient()
    settings = make_test_settings(
        **LLM, llm_base_url='http://127.0.0.1:1234/v1', llm_timeout_seconds=30, llm_supports_reasoning=False
    )

    provider = build_provider(settings, client)

    assert provider.client is client
    assert provider.base_url == 'http://127.0.0.1:1234/v1'
    assert provider.model == 'gemma4:26b'
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
    assert isinstance(llm.state.narrator, LLMNarrator)


def test_the_model_is_called_with_the_client_the_app_closes():
    app = create_app(make_test_settings(**LLM))

    # 앱이 꺼질 때 이 클라이언트를 닫는다(lifespan). 따로 만든 클라이언트면 닫히지 않고 남는다
    assert app.state.narrator.provider.client is app.state.http_client
