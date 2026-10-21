# shared/ai-core/tests/test_calls.py

"""
AI 호출의 기록(ai_core/calls.py) 가운데 보낸 메시지의 지문(HMAC)을 검증한다.

기록을 DB 에 쓰는 기록장은 게임 서버의 테스트(trpg-server/tests/test_call_log.py)가 본다.
"""

import pytest

from ai_core.calls import input_digest
from ai_core.provider import ChatMessage, Role

# --- 입력의 지문 ---

MESSAGES = [
    ChatMessage(Role.SYSTEM, '너는 GM 이다. 악역영애는 사실 경찰의 끄나풀이다.'),
    ChatMessage(Role.USER, '달린다.'),
]


def test_the_digest_is_an_hmac_of_the_messages():
    digest = input_digest(MESSAGES, b'server-key')

    assert digest is not None
    assert len(digest) == 64
    # 같은 입력이면 같은 지문이다. 두 호출이 같은 입력이었는지 알 수 있다
    assert digest == input_digest(list(MESSAGES), b'server-key')


def test_a_different_message_or_key_gives_a_different_digest():
    changed = [MESSAGES[0], ChatMessage(Role.USER, '멈춘다.')]

    assert input_digest(changed, b'server-key') != input_digest(MESSAGES, b'server-key')
    # 키를 모르면 같은 입력으로도 지문을 맞출 수 없다. 내용을 대입해 확인하지 못한다
    assert input_digest(MESSAGES, b'other-key') != input_digest(MESSAGES, b'server-key')


def test_the_role_is_part_of_the_digest():
    as_assistant = [MESSAGES[0], ChatMessage(Role.ASSISTANT, '달린다.')]

    assert input_digest(as_assistant, b'server-key') != input_digest(MESSAGES, b'server-key')


@pytest.mark.parametrize('key', [None, b''])
def test_without_a_key_there_is_no_digest(key: bytes | None):
    assert input_digest(MESSAGES, key) is None
