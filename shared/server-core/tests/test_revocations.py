# shared/server-core/tests/test_revocations.py

"""
끊긴 세션의 목록(server_core/auth/revocations.py, #274)을 검증한다.

  - 목록의 모양: 한 줄이라도 틀리면 통째로 받지 않는다
  - 기억: 받지 못하면 마지막 목록을 쓴다. 한 번도 받지 못했으면 아무것도 끊긴 것으로 보지 않는다
  - API: 끊긴 세션의 토큰은 401 이다. 세션 버전(ver)이 min_ver 이상이면 통한다
  - 설정: 목록의 주소는 공개키 주소 옆이다. 알 수 없으면 뜨지 않는다
"""

import asyncio
import logging

import httpx
import pytest
from fastapi import FastAPI, status
from httpx import AsyncClient
from pydantic import ValidationError

from server_core.auth import revocations
from server_core.auth.revocations import (
    FETCH_ERROR_CODE,
    RevocationList,
    RevocationsFetchError,
    digest_subject,
    parse_revocations,
)
from server_core.testing.tokens import (
    TEST_USER_ID,
    FakeAuthServer,
    SigningKey,
    make_access_claims,
    make_token,
    revoked_entry,
)
from tests.conftest import ME_URL, make_test_settings

REVOCATIONS_URL = 'http://auth.test/api/v1/auth/session-revocations'
SUBJECT = str(TEST_USER_ID)
OTHER_SUBJECT = '0d3f7a52-6f0a-4c1e-9d55-2b8a4c1f7e90'


def bearer(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def make_list(auth_server: FakeAuthServer) -> RevocationList:
    return RevocationList(auth_server.make_client(), REVOCATIONS_URL)


# --- 목록의 모양 ---


def test_the_digest_is_the_sha256_of_the_subject_as_written():
    # 인증 서버 README 의 예와 같다
    assert digest_subject(OTHER_SUBJECT) == '08f6625d1aecc747bd6122bbf85ef9fb3fc0f25f7986169f057f12639fe6c0ed'


def test_reads_the_lines_and_keeps_the_highest_version_of_a_person():
    document = {'revocations': [revoked_entry(SUBJECT, 2), revoked_entry(SUBJECT, 5), revoked_entry(OTHER_SUBJECT, 1)]}

    assert parse_revocations(document) == {digest_subject(SUBJECT): 5, digest_subject(OTHER_SUBJECT): 1}


def test_an_empty_list_is_a_list():
    assert parse_revocations({'revocations': []}) == {}


@pytest.mark.parametrize(
    'document',
    [
        [],
        {},
        {'revocations': None},
        {'revocations': {}},
    ],
)
def test_rejects_a_document_that_is_not_a_list_of_revocations(document: object):
    with pytest.raises(RevocationsFetchError):
        parse_revocations(document)


@pytest.mark.parametrize(
    'bad_line',
    [
        'line',
        {'min_ver': 3},
        {'sub_sha256': 'abc', 'min_ver': 3},
        {'sub_sha256': digest_subject(SUBJECT).upper(), 'min_ver': 3},
        {'sub_sha256': digest_subject(SUBJECT)},
        {'sub_sha256': digest_subject(SUBJECT), 'min_ver': '3'},
        {'sub_sha256': digest_subject(SUBJECT), 'min_ver': -1},
        {'sub_sha256': digest_subject(SUBJECT), 'min_ver': True},
        {'sub_sha256': digest_subject(SUBJECT), 'min_ver': 3.0},
    ],
)
def test_one_bad_line_rejects_the_whole_document(bad_line: object):
    # 틀린 줄만 건너뛰면 그 사람의 끊긴 세션이 조용히 통한다
    document = {'revocations': [revoked_entry(OTHER_SUBJECT, 1), bad_line]}

    with pytest.raises(RevocationsFetchError):
        parse_revocations(document)


# --- 기억 ---


async def test_a_version_below_the_line_is_revoked(auth_server: FakeAuthServer):
    auth_server.revocations = [revoked_entry(SUBJECT, 3)]
    listed = make_list(auth_server)

    assert await listed.refresh()

    assert listed.is_revoked(SUBJECT, 2)
    assert not listed.is_revoked(SUBJECT, 3)
    assert not listed.is_revoked(OTHER_SUBJECT, 0)


async def test_nothing_is_revoked_before_the_first_fetch(auth_server: FakeAuthServer):
    auth_server.revocations = [revoked_entry(SUBJECT, 3)]

    assert not make_list(auth_server).is_revoked(SUBJECT, 0)


async def test_a_failed_fetch_keeps_the_last_list(auth_server: FakeAuthServer, caplog: pytest.LogCaptureFixture):
    auth_server.revocations = [revoked_entry(SUBJECT, 3)]
    listed = make_list(auth_server)
    await listed.refresh()
    auth_server.down = True

    with caplog.at_level(logging.WARNING, logger=revocations.__name__):
        assert not await listed.refresh()

    assert listed.is_revoked(SUBJECT, 2)
    [record] = [entry for entry in caplog.records if entry.name == revocations.__name__]
    assert record.error_code == FETCH_ERROR_CODE
    assert record.reason == 'ConnectError'


async def test_a_bad_document_keeps_the_last_list(auth_server: FakeAuthServer):
    auth_server.revocations = [revoked_entry(SUBJECT, 3)]
    listed = make_list(auth_server)
    await listed.refresh()
    auth_server.revocations = [revoked_entry(OTHER_SUBJECT, 1), {'sub_sha256': 'abc', 'min_ver': 1}]

    assert not await listed.refresh()

    assert listed.is_revoked(SUBJECT, 2)
    assert not listed.is_revoked(OTHER_SUBJECT, 0)


async def test_a_newer_list_replaces_the_old_one(auth_server: FakeAuthServer):
    # 줄은 15분 뒤에 빠진다. 빠진 줄은 이 서버에서도 빠진다
    auth_server.revocations = [revoked_entry(SUBJECT, 3)]
    listed = make_list(auth_server)
    await listed.refresh()
    auth_server.revocations = []

    await listed.refresh()

    assert not listed.is_revoked(SUBJECT, 2)


async def test_rejects_a_document_that_is_too_large(monkeypatch: pytest.MonkeyPatch, auth_server: FakeAuthServer):
    monkeypatch.setattr(revocations, 'MAX_DOCUMENT_BYTES', 64)
    auth_server.revocations = [revoked_entry(SUBJECT, 3)]

    with pytest.raises(RevocationsFetchError, match='too_large'):
        await revocations.fetch_revocations(auth_server.make_client(), REVOCATIONS_URL)


async def test_rejects_an_answer_that_is_not_json():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text='<html>')))

    with pytest.raises(RevocationsFetchError, match='invalid_json'):
        await revocations.fetch_revocations(client, REVOCATIONS_URL)


async def test_rejects_an_error_status():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503)))

    with pytest.raises(RevocationsFetchError, match='HTTPStatusError'):
        await revocations.fetch_revocations(client, REVOCATIONS_URL)


async def test_the_loop_fetches_at_once_and_stops(auth_server: FakeAuthServer):
    auth_server.revocations = [revoked_entry(SUBJECT, 3)]
    listed = RevocationList(auth_server.make_client(), REVOCATIONS_URL, interval=3600)

    running = revocations.start(listed)
    for _ in range(10):
        await asyncio.sleep(0)
    await asyncio.wait_for(running.halt(), timeout=1)

    # 30초를 기다리지 않고 뜨자마자 받는다
    assert listed.is_revoked(SUBJECT, 2)
    assert running.task.done()


# --- API ---


async def test_a_revoked_session_is_unauthorized(
    app: FastAPI, client: AsyncClient, signing_key: SigningKey, auth_server: FakeAuthServer
):
    auth_server.revocations = [revoked_entry(SUBJECT, 3)]
    await app.state.revocations.refresh()
    token = make_token(signing_key, make_access_claims(ver=2))

    response = await client.get(ME_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers['WWW-Authenticate'] == 'Bearer'


async def test_a_session_after_the_cut_is_accepted(
    app: FastAPI, client: AsyncClient, signing_key: SigningKey, auth_server: FakeAuthServer
):
    # 끊은 뒤에 다시 로그인한 세션이다
    auth_server.revocations = [revoked_entry(SUBJECT, 3)]
    await app.state.revocations.refresh()
    token = make_token(signing_key, make_access_claims(ver=3))

    response = await client.get(ME_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_200_OK


async def test_a_token_without_a_version_is_version_zero(
    app: FastAPI, client: AsyncClient, signing_key: SigningKey, auth_server: FakeAuthServer
):
    auth_server.revocations = [revoked_entry(SUBJECT, 1)]
    await app.state.revocations.refresh()
    token = make_token(signing_key, make_access_claims())

    response = await client.get(ME_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.parametrize('version', ['3', -1, True, 1.5, None])
async def test_a_version_of_the_wrong_shape_is_unauthorized(
    client: AsyncClient, signing_key: SigningKey, version: object
):
    # 목록이 비어 있어도 거부한다. 틀린 값을 0 으로 읽으면 끊긴 세션이 통할 수 있다
    token = make_token(signing_key, make_access_claims(ver=version))

    response = await client.get(ME_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_others_are_not_affected(
    app: FastAPI, client: AsyncClient, signing_key: SigningKey, auth_server: FakeAuthServer
):
    auth_server.revocations = [revoked_entry(OTHER_SUBJECT, 5)]
    await app.state.revocations.refresh()
    token = make_token(signing_key, make_access_claims(ver=0))

    response = await client.get(ME_URL, headers=bearer(token))

    assert response.status_code == status.HTTP_200_OK


# --- 설정 ---


def test_the_address_is_next_to_the_jwks_by_default():
    settings = make_test_settings(auth_jwks_url='http://auth.internal:8000/api/v1/auth/jwks')

    assert settings.session_revocations_url == 'http://auth.internal:8000/api/v1/auth/session-revocations'


def test_a_written_address_wins():
    settings = make_test_settings(
        auth_jwks_url='http://keys.internal/keys.json',
        auth_session_revocations_url='http://auth.internal/revoked',
    )

    assert settings.session_revocations_url == 'http://auth.internal/revoked'


def test_does_not_start_without_a_way_to_find_the_address():
    with pytest.raises(ValidationError, match='AUTH_SESSION_REVOCATIONS_URL'):
        make_test_settings(auth_jwks_url='http://keys.internal/keys.json')
