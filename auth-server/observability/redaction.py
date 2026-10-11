# auth-server/observability/redaction.py

"""
로그에 적히기 직전에 민감한 값을 가리는 마지막 방어선. 다른 것을 모르는 순수한 함수들이다.

로그를 남기는 코드가 민감한 값을 넘기지 않는 것이 먼저다. 여기는 실수로 넘어온 것을 막는다.
막는 길은 셋이다.
  1. 칸의 이름을 본다. password, token 같은 이름의 칸은 값을 보지 않고 가린다.
  2. 값의 글을 본다. 토큰, Authorization 머리말의 값, 주소에 든 계정과 비밀번호, 이메일 주소의 모양을 가린다.
  3. 값의 종류를 본다. 글자, 숫자, 참거짓만 싣는다. 묶음(dict, list)과 객체는 풀어 적지 않고 종류의 이름만 적는다.
     묶음을 통째로 적으면 그 안의 무엇이 로그에 남는지 아무도 알 수 없다.

무엇을 로그에 적으면 안 되는지는 docs/observability.md 의 "민감정보"에 있다.
"""

import math
import re

# 가린 자리에 적는 말
REDACTED = '[REDACTED]'
# 칸 하나에 싣는 글의 최대 길이. 넘으면 자른다. 본문 같은 긴 글이 통째로 실리는 것을 막는다
MAX_VALUE_LENGTH = 500
# 메시지의 최대 길이
MAX_MESSAGE_LENGTH = 2000
# 예외의 기록(stack trace)의 최대 길이
MAX_STACK_LENGTH = 16000
# 자른 자리에 붙이는 표시
TRUNCATED = '…'

# 이름에 이 낱말이 들어 있는 칸은 가린다. 이름은 낱말로 쪼개서 본다(access_token -> access, token)
SENSITIVE_WORDS = frozenset({
    'password', 'passwd', 'secret', 'token', 'jwt', 'authorization', 'cookie', 'credential', 'credentials',
    'otp', 'dsn', 'email', 'prompt', 'card', 'cvc', 'cvv', 'code', 'signature',
})  # fmt: skip
# 이름에 이 낱말들이 잇달아 들어 있는 칸은 가린다
SENSITIVE_PHRASES = (
    'api_key', 'private_key', 'access_key', 'payment_key', 'database_url', 'redis_url', 'set_cookie',
)  # fmt: skip
# 이 이름의 칸은 가린다. 글의 원문이 담기는 이름들이다
SENSITIVE_NAMES = frozenset({
    'body', 'content', 'text', 'title', 'declaration', 'memo', 'note', 'notes', 'lore', 'completion', 'response',
    'headers', 'request_body', 'response_body',
})  # fmt: skip
# 이름이 이 낱말로 끝나면 가리지 않는다. 원문이 아니라 그것을 가리키거나 센 값이다(email_hash, prompt_version)
SAFE_LAST_WORDS = frozenset({'hash', 'masked', 'count', 'length', 'version', 'id', 'ms', 'seconds', 'type'})
# code 로 끝나지만 가리지 않는 이름. 인증 코드가 아니라 결과의 종류다
SAFE_NAMES = frozenset({'error_code', 'status_code', 'exit_code'})

# 이름을 낱말로 쪼갤 때 쓰는 모양. 밑줄, 점, 붙임표, 빈칸에서 끊고 대문자 앞에서도 끊는다(accessToken)
_WORD_BREAK = re.compile(r'[_.\-\s]+|(?<=[a-z0-9])(?=[A-Z])')

# JWT 의 모양. 점으로 이은 세 마디고 첫 마디가 eyJ 로 시작한다
_JWT = re.compile(r'eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*')
# Authorization 머리말의 값
_AUTH_SCHEME = re.compile(r'\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}', re.IGNORECASE)
# 주소에 든 계정과 비밀번호(postgres://계정:비밀번호@호스트)
_URL_USERINFO = re.compile(r'://[^/\s:@]+:[^@\s/]+@')
# 이메일 주소
_EMAIL = re.compile(r'([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})')


def words_of(name: str) -> list[str]:
    """칸의 이름을 소문자 낱말들로 쪼갠다."""
    return [word.lower() for word in _WORD_BREAK.split(name) if word]


def is_sensitive_name(name: str) -> bool:
    """이 이름의 칸은 값을 가려야 하는가."""
    words = words_of(name)
    normalized = '_'.join(words)
    if not words or normalized in SAFE_NAMES or words[-1] in SAFE_LAST_WORDS:
        return False
    if normalized in SENSITIVE_NAMES or any(phrase in normalized for phrase in SENSITIVE_PHRASES):
        return True
    return any(word in SENSITIVE_WORDS for word in words)


def truncate(text: str, limit: int) -> str:
    """limit 자를 넘으면 자르고 표시를 붙인다."""
    return text if len(text) <= limit else text[:limit] + TRUNCATED


def scrub_text(text: str, limit: int = MAX_VALUE_LENGTH) -> str:
    """글에서 민감한 모양을 가리고, 너무 길면 자른다. 자르기를 먼저 한다. 긴 글 전체를 훑지 않는다."""
    text = truncate(text, limit)
    text = _JWT.sub('[REDACTED_JWT]', text)
    text = _AUTH_SCHEME.sub(lambda match: f'{match[1]} {REDACTED}', text)
    text = _URL_USERINFO.sub(f'://{REDACTED}@', text)
    return _EMAIL.sub(lambda match: f'{match[1]}***@{match[2]}', text)


def safe_value(name: str, value: object) -> object:
    """
    칸 하나의 값을 로그에 실어도 되는 값으로 바꾼다.

    이름이 민감하면 가린다. 글자는 민감한 모양을 가린다. 숫자와 참거짓과 None 은 그대로다.
    그 밖의 것(묶음, 객체)은 풀어 적지 않고 종류의 이름만 적는다.
    """
    if is_sensitive_name(name):
        return REDACTED
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        # JSON 에는 무한대와 NaN 이 없다
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        return scrub_text(value)
    return f'[{type(value).__name__}]'
