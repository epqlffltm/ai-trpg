# game-server/tests/test_narrator_setup.py

"""
설정을 보고 서술자를 고르는 규칙(app/rounds/narrator_setup.py)과, 앱에 꽂히는 서술자를 검증한다.
서술 등급마다의 모델들과 방장에게 내주는 등급, 창구를 고르는 것(build_router)의 값도 본다.

모델을 부르지 않는다. 고르고 만드는 것만 본다. 창구를 고르는 규칙은 tests/test_model_routing.py 가 본다.
"""

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.ai.call_log import DbCallLog
from app.ai.routing import ANTHROPIC_KIND, GEMINI_KIND, LOCAL_KIND, OPENAI_KIND, ModelRouter
from app.catalog.lookup import DbModelLookup
from app.main import create_app
from app.rounds.fake_narrator import FakeNarrator
from app.rounds.narrator_setup import build_narrator, build_router, offered_tiers, tier_models
from app.rounds.retrying_narrator import RetryingNarrator
from app.rounds.routed_narrator import RoutedNarrator
from app.rounds.tiered_narrator import TieredNarrator
from app.rounds.tiers import NarrationTier
from tests.conftest import make_test_settings

LLM = {'narrator': 'llm', 'llm_model': 'gemma4:26b'}
PREMIUM = {'llm_premium_model': 'qwen3.6:27b'}


def router_of(settings) -> ModelRouter:
    """그 설정으로 만든, 창구를 고르는 것."""
    return build_router(settings, httpx.AsyncClient(), async_sessionmaker())


def narrator_of(settings):
    """그 설정으로 만든 서술자."""
    return build_narrator(settings, router_of(settings), async_sessionmaker())


def standard(narrator) -> RetryingNarrator:
    """언어 모델의 서술자에서 standard 등급의 서술자."""
    return narrator.narrators[NarrationTier.STANDARD]


def test_the_fake_narrator_is_chosen_by_default():
    assert isinstance(narrator_of(make_test_settings()), FakeNarrator)


def test_the_language_model_narrator_retries_one_model_by_default():
    narrator = narrator_of(make_test_settings(**LLM))

    # 등급으로 고르는 서술자다. premium 의 모델을 적지 않으면 standard 하나뿐이다
    assert isinstance(narrator, TieredNarrator)
    assert set(narrator.narrators) == {NarrationTier.STANDARD}
    # 넘어갈 모델을 적지 않으면 첫 모델 하나를 다시 시도하는 서술자다. 창구는 부를 때 고른다
    assert isinstance(standard(narrator), RetryingNarrator)
    (inner,) = standard(narrator).narrators
    assert isinstance(inner, RoutedNarrator)
    assert inner.model == 'gemma4:26b'


def test_the_fallback_models_follow_the_first_in_order():
    narrator = narrator_of(make_test_settings(**LLM, llm_fallback_models=' gemma4:31b-it-qat, ,qwen3.6:27b '))

    # 빈 이름과 앞뒤 공백은 뺀다. 적은 차례대로 넘어간다
    assert [inner.model for inner in standard(narrator).narrators] == ['gemma4:26b', 'gemma4:31b-it-qat', 'qwen3.6:27b']


def test_one_call_may_take_as_long_as_the_timeout():
    narrator = narrator_of(make_test_settings(**LLM, llm_timeout_seconds=45))

    # 남은 시간을 셀 때 쓴다. 남은 시간이 이보다 짧으면 새로 부르지 않는다
    assert standard(narrator).attempt_timeout == 45


def test_the_router_takes_its_values_from_the_settings():
    client = httpx.AsyncClient()
    factory = async_sessionmaker()
    settings = make_test_settings(
        **LLM, llm_base_url='http://127.0.0.1:1234/v1', llm_timeout_seconds=30, llm_supports_reasoning=False
    )

    router = build_router(settings, client, factory)

    assert router.client is client
    assert (router.local.base_url, router.local.api_key, router.local.kind) == (
        'http://127.0.0.1:1234/v1',
        None,
        LOCAL_KIND,
    )
    assert router.timeout == 30
    assert router.local_options.supports_reasoning is False
    # 모델 목록은 부를 때마다 앱의 DB 에서 읽는다
    assert isinstance(router.lookup, DbModelLookup)
    assert router.lookup.session_factory is factory


def test_without_a_key_there_is_no_openai_endpoint():
    assert router_of(make_test_settings(**LLM)).openai is None


def test_the_openai_endpoint_carries_the_key_of_the_settings():
    router = router_of(make_test_settings(**LLM, openai_api_key='sk-test'))

    assert (router.openai.base_url, router.openai.kind) == ('https://api.openai.com/v1', OPENAI_KIND)
    assert router.openai.api_key.get_secret_value() == 'sk-test'
    # 비밀값이라 찍어도 보이지 않는다
    assert 'sk-test' not in repr(router)


def test_without_a_claude_key_there_is_no_anthropic_endpoint():
    assert router_of(make_test_settings(**LLM)).anthropic is None


def test_the_anthropic_endpoint_carries_the_key_of_the_settings():
    router = router_of(make_test_settings(**LLM, anthropic_api_key='sk-ant-test'))

    assert (router.anthropic.base_url, router.anthropic.kind) == ('https://api.anthropic.com', ANTHROPIC_KIND)
    assert router.anthropic.api_key.get_secret_value() == 'sk-ant-test'
    assert 'sk-ant-test' not in repr(router)


def test_the_gemini_endpoint_carries_the_key_of_the_settings():
    router = router_of(make_test_settings(**LLM, gemini_api_key='g-test'))

    assert (router.gemini.base_url, router.gemini.kind) == ('https://generativelanguage.googleapis.com', GEMINI_KIND)
    assert router.gemini.api_key.get_secret_value() == 'g-test'
    assert router_of(make_test_settings(**LLM)).gemini is None


def test_the_key_is_a_secret_in_the_settings():
    settings = make_test_settings(openai_api_key='sk-test')

    assert isinstance(settings.openai_api_key, SecretStr)
    assert 'sk-test' not in repr(settings)


def test_tests_use_the_fake_narrator_whatever_the_env_file_says(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('NARRATOR', 'llm')
    monkeypatch.setenv('LLM_MODEL', 'gemma4:26b')

    # 개발자가 .env 에 언어 모델을 켜 두어도 테스트는 실제 모델을 부르지 않는다
    assert make_test_settings().narrator == 'fake'


def test_the_app_plugs_in_the_chosen_narrator():
    fake = create_app(make_test_settings())
    llm = create_app(make_test_settings(**LLM))

    assert isinstance(fake.state.narrator, FakeNarrator)
    assert isinstance(llm.state.narrator, TieredNarrator)


def test_every_model_is_routed_by_the_router_of_the_app():
    app = create_app(make_test_settings(**LLM, llm_fallback_models='gemma4:31b-it-qat'))

    # 창구를 고르는 것은 앱에 하나다. 앱의 클라이언트로 부른다. 앱이 꺼질 때 그 클라이언트를 닫는다(lifespan)
    assert app.state.model_router.client is app.state.http_client
    for inner in standard(app.state.narrator).narrators:
        assert inner.router is app.state.model_router


def test_every_model_call_is_recorded_in_the_database_of_the_app():
    app = create_app(make_test_settings(**LLM, llm_fallback_models='gemma4:31b-it-qat'))

    # 기록 없이 모델을 부르는 길이 없다. 넘어간 모델의 호출도 앱의 세션 틀로 ai_invocations 에 쓴다
    for inner in standard(app.state.narrator).narrators:
        assert isinstance(inner.log, DbCallLog)
        assert inner.log.session_factory is app.state.session_factory


def test_every_model_signs_its_input_with_the_key_of_the_settings():
    narrator = narrator_of(make_test_settings(**LLM, llm_fallback_models='gemma4:31b-it-qat', ai_log_hmac_key='k'))

    assert [inner.digest_key for inner in standard(narrator).narrators] == [b'k', b'k']


def test_without_a_key_no_model_signs():
    assert [inner.digest_key for inner in standard(narrator_of(make_test_settings(**LLM))).narrators] == [None]


# --- 서술 등급 ---


def test_premium_has_its_own_models_in_order():
    settings = make_test_settings(**LLM, **PREMIUM, llm_premium_fallback_models=' gemma4:31b-it-qat, ')

    narrator = narrator_of(settings)

    # 등급마다 따로 다시 시도하고 넘어간다. premium 이 실패해도 standard 의 모델로 넘어가지 않는다(값이 다르다)
    premium = narrator.narrators[NarrationTier.PREMIUM]
    assert [inner.model for inner in premium.narrators] == ['qwen3.6:27b', 'gemma4:31b-it-qat']
    assert [inner.model for inner in standard(narrator).narrators] == ['gemma4:26b']


def test_premium_fallbacks_without_a_first_model_offer_nothing():
    settings = make_test_settings(**LLM, llm_premium_model='  ', llm_premium_fallback_models='qwen3.6:27b')

    # 넘어갈 모델만 적은 것은 적지 않은 것이다. 첫 모델이 없으면 내주지 않는다
    assert tier_models(settings) == {NarrationTier.STANDARD: ['gemma4:26b']}


def test_the_language_model_offers_only_the_tiers_with_models():
    assert offered_tiers(make_test_settings(**LLM)) == {NarrationTier.STANDARD}
    assert offered_tiers(make_test_settings(**LLM, **PREMIUM)) == {NarrationTier.STANDARD, NarrationTier.PREMIUM}


def test_the_fake_narrator_offers_every_tier():
    # 가짜는 모델을 부르지 않는다. 등급을 고르는 흐름을 모델 없이 해 볼 수 있다
    assert offered_tiers(make_test_settings()) == set(NarrationTier)


def test_the_app_plugs_in_the_offered_tiers():
    assert create_app(make_test_settings(**LLM)).state.narration_tiers == {NarrationTier.STANDARD}
    assert create_app(make_test_settings()).state.narration_tiers == set(NarrationTier)


def test_premium_models_are_routed_and_recorded_by_the_app():
    app = create_app(make_test_settings(**LLM, **PREMIUM))

    for inner in app.state.narrator.narrators[NarrationTier.PREMIUM].narrators:
        assert inner.router is app.state.model_router
        assert inner.log.session_factory is app.state.session_factory


def test_tests_never_hold_the_key_of_the_env_file(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-real')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-real')
    monkeypatch.setenv('GEMINI_API_KEY', 'g-real')

    # 개발자의 .env 에 진짜 키가 있어도 테스트는 실제 API 를 부르지 않는다
    settings = make_test_settings()
    keys = (settings.openai_api_key, settings.anthropic_api_key, settings.gemini_api_key)
    assert [key.get_secret_value() for key in keys] == ['', '', '']
