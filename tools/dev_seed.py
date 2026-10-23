# tools/dev_seed.py

"""
로컬 compose 에 화면을 손으로 볼 거리를 채운다. 시험 계정 둘, 공개된 견본 시나리오 하나, 로비에 보이는 견본 테이블 하나.
표준 라이브러리만 쓴다. 개발 환경에서만 돈다.

화면(web/)을 실제 서버에 붙여 보려면 공개된 시나리오와 계정 둘이 있어야 한다(탐색, 로비, 테이블 방, 스트림).
시나리오를 만드는 화면(B9)이 아직 없어 손으로 하면 API 를 여러 번 불러야 한다. 이것이 그 일을 한 번에 한다.

하는 일:
  1. 인증 서버의 컨테이너에서 dev_seed_accounts.py 를 돌려 시험 계정 둘(방장, 손님)을 만들고 access 토큰을 받는다.
     개발 환경(APP_ENVIRONMENT=development)이 아니면 거기서 멈춘다. 로그인의 메일 코드는 거치지 않는다
  2. 두 계정을 가짜 본인확인 업체의 토큰으로 본인인증한다(POST /identity/verify, 성년의 생일).
     인증 서버가 결제 서버에 알려 충전(A7)을 할 수 있고, 환영 실버를 받는다. 이미 했으면 넘어간다.
     가짜 업체는 개발 환경에서만 있다(auth-server/README.md 의 "본인인증 (가짜 업체)")
  3. 방장의 토큰으로 프록시를 거쳐 게임 서버를 부른다. 고를 수 있는 서술 모델 하나, 룰북(SRD5),
     로어북(장소, 물건, 인물, 사건. dev_seed_world.py), 시나리오(스타팅 둘, 프리젠 셋, 맵, 물건, NPC, 퀘스트),
     소개 페이지(한 줄 소개, 장르, 태그)를 만들고 게시해 공개한다.
     이미 있으면(제목으로 찾는다) 만들지 않는다. 맵이나 화폐가 없는 앞의 견본이면 세계를 넣고 새 판을 게시한다
  4. 방장이 로비에 보이는 견본 테이블을 연다. 모집 중인 것이 이미 있으면 열지 않는다.
     맵이나 화폐가 없는 앞의 판으로 연 것이면 새로 연다
  5. 계정과 주소를 찍는다. 화면에서 로그인하면 메일 코드는 auth-mail 의 로그에 찍힌다(메일 서버를 적지 않았을 때)

몇 번 돌려도 같다. 계정의 비밀번호만 다시 정한다.

쓰는 법(저장소 루트에서, compose 를 --profile app 으로 띄운 뒤):
  uv run --no-project python tools/dev_seed.py
  uv run --no-project python tools/dev_seed.py --password 다른비밀번호 --no-table
"""

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dev_seed_world import ENTRIES, LOREBOOK_TITLE, is_current, sheet, world_fields

REPO_ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_SCRIPT = REPO_ROOT / 'tools' / 'dev_seed_accounts.py'
RESULT_PREFIX = 'SEED_RESULT '

DEFAULT_PASSWORD = 'seed-pass-2026'
LOCAL_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})
GAME = '/api/v1/game'

SEED_TITLE = '[견본] 잿빛 수도원'

# 본인인증(가짜 업체). 토큰은 fake:<DI>:<생일> 이다. 생일은 성년이라 결제(충전)를 할 수 있다
IDENTITY_PATH = '/api/v1/auth/identity/verify'
IDENTITY_TOKEN_PREFIX = 'fake:'
ADULT_BIRTHDAY = '1990-01-01'
TABLE_TITLE = '[견본] 목요일 모임'

# 계정. 아이디와 닉네임은 인증 서버의 규칙(영문 소문자·숫자·밑줄 4~20 자, 닉네임 2~20 자)에 맞는다
ACCOUNTS = (
    {'username': 'seed_host', 'nickname': '견본방장', 'email': 'seed-host@example.com'},
    {'username': 'seed_guest', 'nickname': '견본손님', 'email': 'seed-guest@example.com'},
)


class SeedError(Exception):
    """채우지 못했다. 까닭을 사람이 읽을 글로 싣는다. 서버가 답했으면 그 상태(status)와 오류의 이름(code)도 싣는다."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class Account:
    username: str
    public_id: str
    access_token: str


@dataclass(frozen=True)
class Seeded:
    accounts: list[Account]
    scenario_id: str
    # created(새로 만듦), upgraded(맵이나 화폐가 없던 앞의 견본에 세계를 넣음), kept(이미 있었음)
    scenario_state: str
    table: dict | None


# --- 주소와 인자 ---


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='로컬 compose 에 시험 계정, 견본 시나리오, 견본 테이블을 채운다')
    parser.add_argument('--proxy', default=None, help='프록시의 주소. 비우면 루트 .env 의 PROXY_PORT(없으면 8080)')
    parser.add_argument('--password', default=DEFAULT_PASSWORD, help='두 계정의 비밀번호')
    parser.add_argument('--no-table', action='store_true', help='견본 테이블을 열지 않는다')
    return parser.parse_args(argv)


def proxy_port(env_text: str) -> str:
    """루트 .env 의 PROXY_PORT. 주석이거나 없으면 8080(compose 의 기본값)."""
    for line in env_text.splitlines():
        key, _, value = line.strip().partition('=')
        if key == 'PROXY_PORT' and value.strip():
            return value.strip()
    return '8080'


def default_proxy(repo_root: Path) -> str:
    env_file = repo_root / '.env'
    text = env_file.read_text(encoding='utf-8') if env_file.exists() else ''
    return f'http://127.0.0.1:{proxy_port(text)}'


def ensure_local(url: str) -> None:
    """이 PC 의 프록시만 받는다. 다른 곳(staging 의 도메인)에 시험 계정과 견본을 만들지 않는다."""
    host = urlsplit(url).hostname
    if host not in LOCAL_HOSTS:
        raise SeedError(f'이 PC 의 주소만 받는다(받은 것: {host}). 127.0.0.1 이나 localhost 로 적는다')


# --- 계정(인증 서버의 컨테이너) ---


def account_specs(password: str) -> list[dict]:
    return [{**account, 'password': password} for account in ACCOUNTS]


def parse_seed_result(output: str) -> list[Account]:
    """셸의 출력에서 RESULT_PREFIX 로 시작하는 마지막 줄을 읽는다. Django 의 경고 같은 다른 줄은 건너뛴다."""
    lines = [line for line in output.splitlines() if line.startswith(RESULT_PREFIX)]
    if not lines:
        raise SeedError('계정을 만든 결과를 받지 못했다. 위의 출력을 본다')
    return [Account(**entry) for entry in json.loads(lines[-1][len(RESULT_PREFIX) :])]


def seed_accounts(password: str) -> list[Account]:
    """
    인증 서버의 컨테이너에서 dev_seed_accounts.py 를 돌린다. compose 의 auth-server 가 떠 있어야 한다.
    서버들은 프로필 app 에 있어 --profile app 을 붙인다(루트 .env 의 COMPOSE_PROFILES 로 골랐어도 같다).
    파일의 글을 shell -c 로 넘긴다. 표준 입력으로 넣으면 Django 가 입력이 아직 오지 않았다고 보고 대화형 셸을 열 수 있다
    """
    command = [
        'docker', 'compose', '--profile', 'app', 'exec', '-T',
        '-e', f'SEED_ACCOUNTS={json.dumps(account_specs(password))}',
        'auth-server', 'python', 'manage.py', 'shell', '-c', ACCOUNTS_SCRIPT.read_text(encoding='utf-8'),
    ]  # fmt: skip
    done = subprocess.run(command, capture_output=True, cwd=REPO_ROOT, check=False)
    output = done.stdout.decode('utf-8', 'replace')
    if done.returncode != 0:
        raise SeedError(f'계정을 만들지 못했다\n{output}{done.stderr.decode("utf-8", "replace")}')
    return parse_seed_result(output)


# --- 게임 서버(프록시를 거쳐) ---


def call(proxy: str, token: str, method: str, path: str, body: dict | None = None) -> dict:
    """게임 서버를 부르고 JSON 을 돌려준다. 204 면 빈 dict. 실패하면 상태와 본문을 SeedError 로 싣는다."""
    data = None if body is None else json.dumps(body).encode('utf-8')
    request = urllib.request.Request(f'{proxy}{path}', data=data, method=method)
    request.add_header('Authorization', f'Bearer {token}')
    request.add_header('Accept', 'application/json')
    if data is not None:
        request.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        text = error.read().decode('utf-8', 'replace')
        raise SeedError(f'{method} {path} → {error.code}: {text}', status=error.code, code=error_code(text)) from error
    except urllib.error.URLError as error:
        hint = 'compose 를 --profile app 으로 띄웠는지 본다'
        raise SeedError(f'{proxy} 에 닿지 못했다({error.reason}). {hint}') from error
    return json.loads(raw) if raw else {}


def error_code(text: str) -> str | None:
    """오류 본문의 이름(code). JSON 이 아니거나 없으면 None"""
    try:
        body = json.loads(text)
    except ValueError:
        return None
    return body.get('code') if isinstance(body, dict) and isinstance(body.get('code'), str) else None


def identity_token(account: Account) -> str:
    """가짜 본인확인 업체의 토큰. 계정마다 다른 사람(DI)이고 성년이다. 같은 계정이면 늘 같은 토큰이다"""
    return f'{IDENTITY_TOKEN_PREFIX}{account.username}:{ADULT_BIRTHDAY}'


def verify_identity(proxy: str, account: Account) -> str:
    """본인인증을 한다. verified(이번에 함) 또는 already(이미 했음). 그 밖의 실패는 SeedError"""
    try:
        call(proxy, account.access_token, 'POST', IDENTITY_PATH, {'token': identity_token(account)})
    except SeedError as error:
        if error.status == 409 and error.code == 'identity_already_verified':
            return 'already'
        raise
    return 'verified'


def pick_model(models: dict) -> str:
    """고를 수 있는 서술 모델 중 첫째. 없으면 모델을 들여오고 켜는 법을 알린다."""
    offered = models.get('models') or []
    if not offered:
        raise SeedError(
            '고를 수 있는 서술 모델이 없다. 먼저 들여오고 하나를 켠다:\n'
            '  docker compose --profile app exec trpg-server python -m scripts.models sync\n'
            '  docker compose --profile app exec trpg-server python -m scripts.models enable <이름표>'
        )
    return offered[0]['slug']


def scenario_fields(model: str, world: dict) -> dict:
    """
    견본 시나리오의 칸(제목과 룰북 말고). 스타팅 둘, 다섯 방식 모두, 추천 인원 2~4명에 세계(world_fields)를 더한다.
    스타팅에 문지기와 행상이 나와 첫 장면부터 겨누고 거래할 인물이 있다(장면에 나온 인물만 고를 수 있다).
    능력치를 정하는 방식의 최대 HP 는 8 에 건강의 보정, 20 까지
    """
    return {
        'narration_model': model,
        'description': '화면을 손으로 보려고 만든 견본이다(tools/dev_seed.py).',
        'openings': [
            (
                '비가 내리는 밤, 수도원의 문 앞에 선다. 종은 울리지 않는다. 문 옆에 늙은 문지기가 등불을 들고 서 있다. '
                '처마 밑에서는 떠돌이 행상이 젖은 짐을 푼다.'
            ),
            (
                '이미 수도원 안이다. 등 뒤에서 문이 스스로 닫힌다. 늙은 문지기가 어둠 속에서 너희를 본다. '
                '구석의 행상이 손을 흔든다.'
            ),
        ],
        'default_sheet': sheet(10),
        'character_modes': ['pregen', 'custom', 'manual', 'point_buy', 'rolled'],
        'player_made_hp': {'base': 8, 'cap': 20},
        'reroll_allowed': True,
        'recommended_players': {'min': 2, 'max': 4},
        **world,
    }


def scenario_body(rulebook_id: str, model: str, world: dict) -> dict:
    """새로 만들 때의 견본 시나리오"""
    return {'title': SEED_TITLE, 'rulebook_id': rulebook_id, **scenario_fields(model, world)}


def listing_body() -> dict:
    return {
        'tagline': '종이 울리지 않는 밤, 수도원의 문이 열린다',
        'description': (
            '마을의 부탁을 받고 버려진 수도원에 간다. 안에서 누군가 노래를 부른다.\n\n'
            '화면을 손으로 보려고 만든 견본이다.'
        ),
        'genres': ['horror', 'mystery'],
        'tags': ['견본', '수도원'],
    }


def table_body(scenario_id: str) -> dict:
    return {'scenario_id': scenario_id, 'capacity': 4, 'is_public': True}


def find_by_title(page: dict, title: str) -> dict | None:
    return next((item for item in page.get('items', []) if item.get('title') == title), None)


def publish(proxy: str, token: str, scenario_id: str) -> None:
    """지금의 내용을 1판으로 굳히고 그 판을 공개한다."""
    version = call(proxy, token, 'POST', f'{GAME}/scenarios/{scenario_id}/versions', {'note': '견본'})
    call(proxy, token, 'PUT', f'{GAME}/scenarios/{scenario_id}/listing/publication', {'version': version['number']})


def is_listed(proxy: str, token: str, scenario_id: str) -> bool:
    try:
        call(proxy, token, 'GET', f'{GAME}/listings/{scenario_id}')
    except SeedError:
        return False
    return True


def seed_lorebook(proxy: str, token: str) -> tuple[str, dict[str, str]]:
    """견본 로어북의 ID 와, 항목의 이름에서 ID 로 가는 표. 없는 로어북과 항목만 만든다(이름으로 찾는다)."""
    found = find_by_title(call(proxy, token, 'GET', f'{GAME}/lorebooks?limit=100'), LOREBOOK_TITLE)
    lorebook = found or call(
        proxy, token, 'POST', f'{GAME}/lorebooks', {'title': LOREBOOK_TITLE, 'description': '견본'}
    )
    path = f'{GAME}/lorebooks/{lorebook["id"]}/entries'
    have = {entry['name']: entry['id'] for entry in call_list(proxy, token, path)} if found else {}
    for entry in ENTRIES:
        if entry['name'] not in have:
            have[entry['name']] = call(proxy, token, 'POST', path, entry)['id']
    return lorebook['id'], have


def call_list(proxy: str, token: str, path: str) -> list[dict]:
    """목록을 돌려주는 주소(로어북의 항목)를 부른다. 목록이 아니면 빈 목록이다"""
    answer = call(proxy, token, 'GET', path)
    return answer if isinstance(answer, list) else []


def seed_world(proxy: str, token: str) -> dict:
    """로어북을 채우고 시나리오에 넣을 세계의 칸을 만든다."""
    lorebook_id, ids = seed_lorebook(proxy, token)
    return world_fields(ids, lorebook_id)


def seed_scenario(proxy: str, token: str) -> tuple[str, str]:
    """
    견본 시나리오의 ID 와 한 일(created, upgraded, kept).
    있고 지금 세계(맵과 화폐, is_current)이면 공개만 확인한다. 앞의 견본이면 세계를 넣고 새 판을 게시한다
    """
    found = find_by_title(call(proxy, token, 'GET', f'{GAME}/scenarios?limit=100'), SEED_TITLE)
    if found and is_current(call(proxy, token, 'GET', f'{GAME}/scenarios/{found["id"]}')):
        if not is_listed(proxy, token, found['id']):
            publish(proxy, token, found['id'])
        return found['id'], 'kept'
    model = pick_model(call(proxy, token, 'GET', f'{GAME}/tables/narration-models'))
    world = seed_world(proxy, token)
    if found:
        call(proxy, token, 'PATCH', f'{GAME}/scenarios/{found["id"]}', scenario_fields(model, world))
        publish(proxy, token, found['id'])
        return found['id'], 'upgraded'
    rulebook = call(proxy, token, 'POST', f'{GAME}/rulebooks', {'title': '[견본] 룰북', 'template': 'srd5'})
    scenario = call(proxy, token, 'POST', f'{GAME}/scenarios', scenario_body(rulebook['id'], model, world))
    call(proxy, token, 'PATCH', f'{GAME}/scenarios/{scenario["id"]}/listing', listing_body())
    publish(proxy, token, scenario['id'])
    return scenario['id'], 'created'


def seed_table(proxy: str, token: str, scenario_id: str) -> dict:
    """
    방장이 앉은 모집 중인 견본 테이블. 이미 있으면 그것을 돌려준다.
    테이블은 열 때의 판을 쓴다. 맵이나 화폐가 없으면 앞의 판으로 연 것이라 새로 연다(앞의 것은 그대로 둔다)
    """
    mine = call(proxy, token, 'GET', f'{GAME}/tables?limit=100')
    for table in mine.get('items', []):
        if table.get('scenario_id') == scenario_id and table.get('status') == 'recruiting':
            detail = call(proxy, token, 'GET', f'{GAME}/tables/{table["id"]}')
            if is_current(detail):
                return detail
    return call(proxy, token, 'POST', f'{GAME}/tables', table_body(scenario_id))


# --- 모으고 찍기 ---


def run(proxy: str, password: str, with_table: bool) -> Seeded:
    ensure_local(proxy)
    accounts = seed_accounts(password)
    for account in accounts:
        verify_identity(proxy, account)
    host = accounts[0]
    scenario_id, state = seed_scenario(proxy, host.access_token)
    table = seed_table(proxy, host.access_token, scenario_id) if with_table else None
    return Seeded(accounts=accounts, scenario_id=scenario_id, scenario_state=state, table=table)


SCENARIO_STATES = {'created': '새로 만들었다', 'upgraded': '맵과 물건을 넣어 새 판을 게시했다', 'kept': '이미 있었다'}


def report(seeded: Seeded, proxy: str, password: str) -> str:
    lines = ['채웠다.', '', '계정(두 계정의 비밀번호가 같다):']
    roles = ('방장', '손님')
    for role, account in zip(roles, seeded.accounts, strict=False):
        lines.append(f'  {role}: {account.username} / {password}')
    state = SCENARIO_STATES[seeded.scenario_state]
    lines += ['', f'시나리오({state}): {proxy}/trpg/scenarios/{seeded.scenario_id}']
    if seeded.table:
        lines += [f'테이블: {proxy}/trpg/tables/{seeded.table["id"]}  초대 코드 {seeded.table.get("invite_code")}']
    lines += [
        '',
        '화면에서 로그인하면 메일 코드가 온다. 메일 서버를 적지 않았으면 로그에 찍힌다:',
        '  docker compose --profile app logs -f auth-mail',
        '두 계정으로 보려면 다른 브라우저나 시크릿 창을 하나 더 쓴다(같은 브라우저의 창은 로그인을 나눈다).',
        '두 계정은 가짜 업체로 본인인증을 했다(성년). 지갑의 충전(시험용 결제창)을 할 수 있다.',
        '한 판을 따라가는 순서는 docs/operations/local-screens.md 의 "한 판 따라가기"에 있다.',
    ]
    return '\n'.join(lines)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    proxy = (args.proxy or default_proxy(REPO_ROOT)).rstrip('/')
    try:
        seeded = run(proxy, args.password, with_table=not args.no_table)
    except SeedError as error:
        print(error, file=sys.stderr)
        return 1
    print(report(seeded, proxy, args.password))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
