# tools/dev_seed.py

"""
로컬 compose 에 화면을 손으로 볼 거리를 채운다. 시험 계정 둘, 공개된 견본 시나리오 하나, 로비에 보이는 견본 테이블 하나.
표준 라이브러리만 쓴다. 개발 환경에서만 돈다.

화면(web/)을 실제 서버에 붙여 보려면 공개된 시나리오와 계정 둘이 있어야 한다(탐색, 로비, 테이블 방, 스트림).
시나리오를 만드는 화면(B9)이 아직 없어 손으로 하면 API 를 여러 번 불러야 한다. 이것이 그 일을 한 번에 한다.

하는 일:
  1. 인증 서버의 컨테이너에서 dev_seed_accounts.py 를 돌려 시험 계정 둘(방장, 손님)을 만들고 access 토큰을 받는다.
     개발 환경(APP_ENVIRONMENT=development)이 아니면 거기서 멈춘다. 로그인의 메일 코드는 거치지 않는다
  2. 방장의 토큰으로 프록시를 거쳐 게임 서버를 부른다. 고를 수 있는 서술 모델 하나, 룰북,
     시나리오(스타팅 둘, 프리젠 셋), 소개 페이지(한 줄 소개, 장르, 태그)를 만들고 1판을 게시해 공개한다.
     이미 있으면(제목으로 찾는다) 만들지 않는다
  3. 방장이 로비에 보이는 견본 테이블을 연다. 모집 중인 것이 이미 있으면 열지 않는다
  4. 계정과 주소를 찍는다. 화면에서 로그인하면 메일 코드는 auth-mail 의 로그에 찍힌다(메일 서버를 적지 않았을 때)

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

REPO_ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_SCRIPT = REPO_ROOT / 'tools' / 'dev_seed_accounts.py'
RESULT_PREFIX = 'SEED_RESULT '

DEFAULT_PASSWORD = 'seed-pass-2026'
LOCAL_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})
GAME = '/api/v1/game'

SEED_TITLE = '[견본] 잿빛 수도원'
TABLE_TITLE = '[견본] 목요일 모임'

# 계정. 아이디와 닉네임은 인증 서버의 규칙(영문 소문자·숫자·밑줄 4~20 자, 닉네임 2~20 자)에 맞는다
ACCOUNTS = (
    {'username': 'seed_host', 'nickname': '견본방장', 'email': 'seed-host@example.com'},
    {'username': 'seed_guest', 'nickname': '견본손님', 'email': 'seed-guest@example.com'},
)

# SRD5 템플릿의 능력치. 모두 10 이면 보정이 0 이다
ABILITY_KEYS = ('str', 'dex', 'con', 'int', 'wis', 'cha')


class SeedError(Exception):
    """채우지 못했다. 까닭을 사람이 읽을 글로 싣는다."""


@dataclass(frozen=True)
class Account:
    username: str
    public_id: str
    access_token: str


@dataclass(frozen=True)
class Seeded:
    accounts: list[Account]
    scenario_id: str
    created_scenario: bool
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
        raise SeedError(f'{method} {path} → {error.code}: {error.read().decode("utf-8", "replace")}') from error
    except urllib.error.URLError as error:
        hint = 'compose 를 --profile app 으로 띄웠는지 본다'
        raise SeedError(f'{proxy} 에 닿지 못했다({error.reason}). {hint}') from error
    return json.loads(raw) if raw else {}


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


def sheet(max_hp: int, **scores: int) -> dict:
    return {'abilities': {key: scores.get(key, 10) for key in ABILITY_KEYS}, 'max_hp': max_hp}


def scenario_body(rulebook_id: str, model: str) -> dict:
    """견본 시나리오. 스타팅 둘, 프리젠 셋, 프리젠과 직접 쓰기를 허용한다. 추천 인원 2~4명."""
    return {
        'title': SEED_TITLE,
        'rulebook_id': rulebook_id,
        'narration_model': model,
        'description': '화면을 손으로 보려고 만든 견본이다(tools/dev_seed.py).',
        'openings': [
            '비가 내리는 밤, 수도원의 문 앞에 선다. 종은 울리지 않는다.',
            '이미 수도원 안이다. 등 뒤에서 문이 스스로 닫힌다.',
        ],
        'default_sheet': sheet(10),
        'pregens': [
            {'name': '수도사 렌', 'description': '말이 없다. 기도문을 외운다.', 'sheet': sheet(12, wis=15, con=12)},
            {'name': '사냥꾼 미라', 'description': '활을 쓴다. 발소리가 없다.', 'sheet': sheet(11, dex=16, wis=12)},
            {'name': '용병 도르', 'description': '도끼를 든다. 돈을 받고 왔다.', 'sheet': sheet(14, str=16, con=14)},
        ],
        'character_modes': ['pregen', 'custom'],
        'recommended_players': {'min': 2, 'max': 4},
    }


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


def seed_scenario(proxy: str, token: str) -> tuple[str, bool]:
    """견본 시나리오의 ID 와 새로 만들었는지. 있으면 공개만 확인한다."""
    found = find_by_title(call(proxy, token, 'GET', f'{GAME}/scenarios?limit=100'), SEED_TITLE)
    if found:
        if not is_listed(proxy, token, found['id']):
            publish(proxy, token, found['id'])
        return found['id'], False
    model = pick_model(call(proxy, token, 'GET', f'{GAME}/tables/narration-models'))
    rulebook = call(proxy, token, 'POST', f'{GAME}/rulebooks', {'title': '[견본] 룰북', 'template': 'srd5'})
    scenario = call(proxy, token, 'POST', f'{GAME}/scenarios', scenario_body(rulebook['id'], model))
    call(proxy, token, 'PATCH', f'{GAME}/scenarios/{scenario["id"]}/listing', listing_body())
    publish(proxy, token, scenario['id'])
    return scenario['id'], True


def seed_table(proxy: str, token: str, scenario_id: str) -> dict:
    """방장이 앉은 모집 중인 견본 테이블. 이미 있으면 그것을 돌려준다."""
    mine = call(proxy, token, 'GET', f'{GAME}/tables?limit=100')
    for table in mine.get('items', []):
        if table.get('scenario_id') == scenario_id and table.get('status') == 'recruiting':
            return call(proxy, token, 'GET', f'{GAME}/tables/{table["id"]}')
    return call(proxy, token, 'POST', f'{GAME}/tables', table_body(scenario_id))


# --- 모으고 찍기 ---


def run(proxy: str, password: str, with_table: bool) -> Seeded:
    ensure_local(proxy)
    accounts = seed_accounts(password)
    host = accounts[0]
    scenario_id, created = seed_scenario(proxy, host.access_token)
    table = seed_table(proxy, host.access_token, scenario_id) if with_table else None
    return Seeded(accounts=accounts, scenario_id=scenario_id, created_scenario=created, table=table)


def report(seeded: Seeded, proxy: str, password: str) -> str:
    lines = ['채웠다.', '', '계정(두 계정의 비밀번호가 같다):']
    roles = ('방장', '손님')
    for role, account in zip(roles, seeded.accounts, strict=False):
        lines.append(f'  {role}: {account.username} / {password}')
    state = '새로 만들었다' if seeded.created_scenario else '이미 있었다'
    lines += ['', f'시나리오({state}): {proxy}/trpg/scenarios/{seeded.scenario_id}']
    if seeded.table:
        lines += [f'테이블: {proxy}/trpg/tables/{seeded.table["id"]}  초대 코드 {seeded.table.get("invite_code")}']
    lines += [
        '',
        '화면에서 로그인하면 메일 코드가 온다. 메일 서버를 적지 않았으면 로그에 찍힌다:',
        '  docker compose --profile app logs -f auth-mail',
        '두 계정으로 보려면 다른 브라우저나 시크릿 창을 하나 더 쓴다(같은 브라우저의 창은 로그인을 나눈다).',
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
