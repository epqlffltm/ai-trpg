# auth-server/config/db_limits.py

"""
DB 연결마다 거는 시간 한도(#1282). FastAPI 서버들(shared/server-core 의 database.py, #1260)과 같은 값과 이름이다.

    DB_LOCK_TIMEOUT_MS                  잠금을 기다리는 가장 긴 시간. 기본 5000(5초)
    DB_STATEMENT_TIMEOUT_MS             쿼리 하나의 가장 긴 시간. 기본 10000(10초)
    DB_IDLE_IN_TRANSACTION_TIMEOUT_MS   트랜잭션을 열어 둔 채 쉬는 가장 긴 시간. 기본 60000(60초)

0 이면 그 한도를 끈다. 인증 서버는 gunicorn 워커가 하나라, 요청 하나가 잠금이나 느린 쿼리에 묶이면
로그인, 토큰 갱신, JWKS 가 모두 멈춘다. 한도는 그 시간을 묶는다.

거는 법: 연결을 맺을 때 넘기는 시작 값(libpq 의 options, "-c 이름=값")이다. 쿼리를 따로 보내지 않고,
연결을 다시 맺어도 늘 붙는다. 테스트 실행기가 만드는 테스트용 DB 의 연결도 같은 OPTIONS 를 받는다.

가르는 법: 요청을 받는 서버(gunicorn 은 config/wsgi.py 로 뜬다)와 워커는 한도를 받는다.
마이그레이션과 한꺼번에 지우는 주기 명령(docker/cron/auth.crontab)은 오래 걸려도 되고 도중에 끊기면 안 된다.
manage.py 가 설정을 읽기 전에 명령의 이름을 보고, 이 목록(UNLIMITED_COMMANDS)의 명령이면 세 값을 0 으로 둔다
(lift_for_command). PC 에서 돌리든 compose 에서 돌리든 같다.

이 파일은 Django 를 가져오지 않는다. manage.py 가 Django 를 띄우기 전에 부른다.
"""

from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass

# 환경 변수의 이름. FastAPI 서버(server-core 의 settings.py)와 같다
LOCK_TIMEOUT_NAME = 'DB_LOCK_TIMEOUT_MS'
STATEMENT_TIMEOUT_NAME = 'DB_STATEMENT_TIMEOUT_MS'
IDLE_IN_TRANSACTION_TIMEOUT_NAME = 'DB_IDLE_IN_TRANSACTION_TIMEOUT_MS'
LIMIT_NAMES = (LOCK_TIMEOUT_NAME, STATEMENT_TIMEOUT_NAME, IDLE_IN_TRANSACTION_TIMEOUT_NAME)

# 한도 없이 DB 에 붙는 명령. 마이그레이션과 docker/cron/auth.crontab 의 주기 명령이다.
# 주기 명령을 더하면 여기에도 더한다. 빠뜨리면 테스트(config/tests/test_db_limits.py)가 실패한다
UNLIMITED_COMMANDS = frozenset(
    {
        'migrate',
        'send_security_digest',
        'delete_unverified_users',
        'flushexpiredtokens',
        'delete_released_nicknames',
        'delete_old_inquiries',
    }
)
# 한도를 끈 값
OFF = '0'


@dataclass(frozen=True)
class Limits:
    """연결 하나를 붙잡아 두는 가장 긴 시간들(밀리초). 0 은 그 한도를 끈다."""

    lock_timeout_ms: int = 5_000
    statement_timeout_ms: int = 10_000
    idle_in_transaction_timeout_ms: int = 60_000


# 한도 없음. 마이그레이션과 주기 명령이 쓴다
NO_LIMITS = Limits(lock_timeout_ms=0, statement_timeout_ms=0, idle_in_transaction_timeout_ms=0)
# 값마다의 상한(밀리초). server-core 의 설정과 같다
UPPER_BOUNDS = {
    LOCK_TIMEOUT_NAME: 600_000,
    STATEMENT_TIMEOUT_NAME: 600_000,
    IDLE_IN_TRANSACTION_TIMEOUT_NAME: 3_600_000,
}


class InvalidLimitError(ValueError):
    """한도의 값이 정수가 아니거나 범위(0~상한) 밖이다."""


def read_limit(environ: Mapping[str, str], name: str, default: int) -> int:
    """환경 변수 하나를 밀리초로 읽는다. 없으면 기본값이다. 범위 밖이면 InvalidLimitError."""
    raw = environ.get(name, '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise InvalidLimitError(f'{name} 은 밀리초(정수)여야 합니다: {raw!r}') from exc
    if not 0 <= value <= UPPER_BOUNDS[name]:
        raise InvalidLimitError(f'{name} 은 0 부터 {UPPER_BOUNDS[name]} 까지입니다: {value}')
    return value


def limits_from(environ: Mapping[str, str]) -> Limits:
    """환경 변수에 적힌 한도. 적지 않은 것은 기본값이다."""
    defaults = Limits()
    return Limits(
        lock_timeout_ms=read_limit(environ, LOCK_TIMEOUT_NAME, defaults.lock_timeout_ms),
        statement_timeout_ms=read_limit(environ, STATEMENT_TIMEOUT_NAME, defaults.statement_timeout_ms),
        idle_in_transaction_timeout_ms=read_limit(
            environ, IDLE_IN_TRANSACTION_TIMEOUT_NAME, defaults.idle_in_transaction_timeout_ms
        ),
    )


def startup_options(limits: Limits) -> str:
    """한도를 연결의 시작 값(libpq 의 options)으로 바꾼다. 단위 없는 숫자는 밀리초다. 0 도 그대로 넘겨 끈다."""
    return ' '.join(
        [
            f'-c lock_timeout={limits.lock_timeout_ms}',
            f'-c statement_timeout={limits.statement_timeout_ms}',
            f'-c idle_in_transaction_session_timeout={limits.idle_in_transaction_timeout_ms}',
        ]
    )


def with_limits(options: Mapping[str, object], limits: Limits) -> dict[str, object]:
    """
    DATABASES 의 OPTIONS 에 한도를 더한 새 dict.

    DATABASE_URL 에 ?options= 로 적은 시작 값이 있으면 지우지 않고 그 뒤에 붙인다. 같은 이름이면 뒤의 것(한도)이 이긴다.
    """
    existing = str(options.get('options', '')).strip()
    merged = f'{existing} {startup_options(limits)}'.strip()
    return {**options, 'options': merged}


def is_unlimited_command(argv: Sequence[str]) -> bool:
    """manage.py 의 인자가 한도 없이 붙는 명령인가. 명령의 이름은 첫 인자다."""
    return len(argv) > 1 and argv[1] in UNLIMITED_COMMANDS


def lift_for_command(argv: Sequence[str], environ: MutableMapping[str, str]) -> bool:
    """
    한도 없이 붙는 명령이면 세 한도를 0 으로 둔다. 설정을 읽기 전에 부른다. 둔 경우 True 다.

    .env 와 compose 에 적은 값보다 앞선다(설정은 이미 있는 환경 변수를 .env 로 덮지 않는다).
    """
    if not is_unlimited_command(argv):
        return False
    for name in LIMIT_NAMES:
        environ[name] = OFF
    return True
