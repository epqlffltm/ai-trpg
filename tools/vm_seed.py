# tools/vm_seed.py

"""
VM(staging)에 테스트할 작품을 채운다. TRPG "꺼진 등대", chat "하람"·"무진", story "소금 시장의 밤".
값은 vm_seed_content.py 에 있다. 표준 라이브러리만 쓴다. 집 PC 에서 돌린다(VM 의 사이트를 브라우저처럼 부른다).

하는 일:
  1. VM 에 SSH 로 붙어 인증 서버의 컨테이너에서 vm_seed_token.py 를 돌려, 만든 사람(운영자)의 access 토큰을 받는다.
     운영 환경이면, 운영자가 아니면, 다시 동의할 것이 남았으면 거기서 멈춘다. 로그인의 메일 코드는 거치지 않는다
  2. 그 토큰으로 사이트(프록시)를 거쳐 게임 서버에 룰북, 로어북, 몬스터 모음, 시나리오를 만들고,
     게시 점검이 통과하면 게시해 공개한다. 점검에 걸리면 그 까닭을 찍고 멈춘다
  3. asset 서버에 로어북을 만들어 게시하고, 캐릭터 둘(하람, 무진)과 세계관 하나를 만들어 공개로 게시한다.
     캐릭터와 세계관은 지금 운영자만 만들고 공개한다
  4. 화면에서 열 주소를 찍는다

몇 번 돌려도 같다. 이름(제목)으로 찾아 이미 게시한 것은 건드리지 않는다. 바꾼 값을 다시 넣으려면 화면에서 지우고 돌린다.
VM 의 인증서는 자체 서명이라 --insecure 를 붙인다. 그것은 이름이 .test 로 끝나는 주소에만 받는다.

    사용(집 PC 의 저장소 루트에서, VM 이 최신 main 이고 운영자 계정이 화면에서 한 번 로그인해 동의를 마친 뒤):
      uv run --no-project python tools/vm_seed.py --creator <운영자 아이디> --insecure
    SSH 를 키 없이 비밀번호로 붙으면 --password 를 더한다. ssh 가 비밀번호를 한 번 묻는다.
"""

import argparse
import json
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import vm_seed_content as content

REPO_ROOT = Path(__file__).resolve().parents[1]
TOKEN_SCRIPT = REPO_ROOT / 'tools' / 'vm_seed_token.py'
RESULT_PREFIX = 'SEED_TOKEN '

DEFAULT_SITE = 'https://staging.ai-trpg.test'
DEFAULT_SSH = 'trpg@staging.ai-trpg.test'
DEFAULT_REPO_DIR = '/srv/ai-trpg'
# 인증 서버의 아이디 규칙(영문 소문자·숫자·밑줄 4~20 자). SSH 의 명령에 넣으므로 이 모양만 받는다
USERNAME_PATTERN = re.compile(r'^[a-z0-9_]{4,20}$')
# 자체 서명 인증서를 받아도 되는 주소의 끝. 시험용 이름(RFC 2606)이라 바깥에 없다
INSECURE_SUFFIX = '.test'
PREFERRED_MODEL = 'gemma4-26b-a4b'

GAME = '/api/v1/game'
ASSET = '/api/v1/asset'

# 서버를 부르는 함수: (방법, 경로, 본문) → JSON. 204 면 빈 dict. 시험은 가짜를 넣는다
Api = Callable[[str, str, dict | None], dict | list]


class SeedError(Exception):
    """채우지 못했다. 까닭을 사람이 읽을 글로 싣는다. 서버가 답했으면 그 상태(status)도 싣는다."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Made:
    """만든 것 하나. state 는 created(새로 만들어 게시함), published(있던 것을 게시함), kept(이미 게시돼 있음)."""

    kind: str
    name: str
    id: str
    state: str


# --- 인자와 주소 ---


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='VM 에 테스트할 TRPG, chat, story 작품을 채운다')
    parser.add_argument('--creator', required=True, help='만든 사람이 될 운영자의 아이디')
    parser.add_argument('--site', default=DEFAULT_SITE, help='사이트의 주소')
    parser.add_argument('--ssh', default=DEFAULT_SSH, help='VM 에 붙을 SSH 의 사용자@주소')
    parser.add_argument('--repo-dir', default=DEFAULT_REPO_DIR, help='VM 의 저장소 폴더')
    parser.add_argument('--insecure', action='store_true', help='자체 서명 인증서를 받는다(.test 주소만)')
    parser.add_argument('--password', action='store_true', help='SSH 를 키 없이 비밀번호로 붙는다(물으면 친다)')
    return parser.parse_args(argv)


def ensure_username(username: str) -> str:
    """SSH 의 명령에 넣을 아이디. 규칙에 맞지 않으면 멈춘다."""
    if not USERNAME_PATTERN.fullmatch(username):
        raise SeedError(f'아이디의 모양이 아니다: {username!r}(영문 소문자·숫자·밑줄 4~20 자)')
    return username


def tls_context(site: str, insecure: bool) -> ssl.SSLContext | None:
    """https 를 부를 때의 TLS. --insecure 면 인증서를 보지 않되, .test 주소에만 허락한다."""
    host = urlsplit(site).hostname or ''
    if not insecure:
        return None
    if not host.endswith(INSECURE_SUFFIX):
        raise SeedError(f'--insecure 는 {INSECURE_SUFFIX} 로 끝나는 주소에만 쓴다(받은 것: {host})')
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


# --- 토큰(VM 의 인증 서버 컨테이너) ---


def token_command(ssh: str, repo_dir: str, creator: str, ask_password: bool = False) -> list[str]:
    """VM 에서 인증 서버의 컨테이너로 토큰 스크립트를 넘기는 명령. 스크립트는 표준 입력으로 간다(python -).

    키로 붙으면 묻는 창 없이(BatchMode) 붙는다. 비밀번호로 붙으면 ssh 가 비밀번호를 묻게 둔다.
    """
    remote = f'cd {repo_dir} && docker compose exec -T -e SEED_CREATOR={creator} auth-server python -'
    options = [] if ask_password else ['-o', 'BatchMode=yes']
    return ['ssh', *options, ssh, remote]


def parse_token(output: str) -> str:
    """출력에서 RESULT_PREFIX 로 시작하는 마지막 줄의 토큰을 읽는다. 경고 같은 다른 줄은 건너뛴다."""
    lines = [line for line in output.splitlines() if line.startswith(RESULT_PREFIX)]
    if not lines:
        raise SeedError('토큰을 받지 못했다. 위의 출력을 본다')
    return json.loads(lines[-1][len(RESULT_PREFIX) :])['access_token']


def mint_token(ssh: str, repo_dir: str, creator: str, ask_password: bool = False) -> str:
    """만든 사람의 access 토큰. 키로 붙거나, ask_password 면 ssh 가 묻는 비밀번호를 친다.

    비밀번호로 붙을 때는 ssh 의 물음이 보이도록 오류 출력을 화면에 그대로 둔다(그때 까닭도 화면에 찍힌다).
    """
    script = TOKEN_SCRIPT.read_bytes()
    stderr = None if ask_password else subprocess.PIPE
    command = token_command(ssh, repo_dir, creator, ask_password)
    done = subprocess.run(command, input=script, stdout=subprocess.PIPE, stderr=stderr, check=False)
    output = done.stdout.decode('utf-8', 'replace')
    if done.returncode != 0:
        detail = (done.stderr or b'').decode('utf-8', 'replace')
        raise SeedError(f'토큰을 받지 못했다\n{output}{detail}')
    return parse_token(output)


# --- 서버 부르기 ---


def http_api(site: str, token: str, context: ssl.SSLContext | None) -> Api:
    """사이트(프록시)를 거쳐 서버를 부르는 함수를 만든다."""

    def call(method: str, path: str, body: dict | None = None) -> dict | list:
        data = None if body is None else json.dumps(body).encode('utf-8')
        request = urllib.request.Request(f'{site}{path}', data=data, method=method)
        request.add_header('Authorization', f'Bearer {token}')
        request.add_header('Accept', 'application/json')
        if data is not None:
            request.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(request, timeout=30, context=context) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            text = error.read().decode('utf-8', 'replace')
            raise SeedError(f'{method} {path} → {error.code}: {text}', status=error.code) from error
        except urllib.error.URLError as error:
            raise SeedError(f'{site} 에 닿지 못했다({error.reason}). VM 과 hosts 를 본다') from error
        return json.loads(raw) if raw else {}

    return call


def items_of(answer: dict | list) -> list[dict]:
    """목록의 답. 쪽(items 가 있는 것)이든 목록이든 받는다."""
    if isinstance(answer, list):
        return answer
    return list(answer.get('items') or [])


def find(answer: dict | list, field: str, value: str) -> dict | None:
    return next((item for item in items_of(answer) if item.get(field) == value), None)


# --- TRPG(게임 서버) ---


def pick_model(answer: dict) -> str:
    """서술 모델. VM 의 로컬 모델이 있으면 그것, 없으면 고를 수 있는 것 중 첫째. 없으면 멈춘다."""
    slugs = [model['slug'] for model in answer.get('models') or []]
    if not slugs:
        raise SeedError('고를 수 있는 서술 모델이 없다. vm-test-plan 의 2-1(모델 넣기), 2-2(가격표)를 먼저 한다')
    return PREFERRED_MODEL if PREFERRED_MODEL in slugs else slugs[0]


def ensure_asset(api: Api, kind: str, title: str, body: dict) -> str:
    """게임 서버의 룰북, 로어북, 몬스터 모음. 제목으로 찾고 없으면 만든다. ID 를 돌려준다."""
    found = find(api('GET', f'{GAME}/{kind}?limit=100', None), 'title', title)
    return found['id'] if found else api('POST', f'{GAME}/{kind}', body)['id']


def ensure_entries(api: Api, lorebook_id: str) -> dict[str, str]:
    """로어북의 항목. 이름으로 찾고 없는 것만 만든다. 이름에서 ID 로 가는 표를 돌려준다."""
    path = f'{GAME}/lorebooks/{lorebook_id}/entries'
    have = {entry['name']: entry['id'] for entry in items_of(api('GET', path, None))}
    for entry in content.ENTRIES:
        if entry['name'] not in have:
            have[entry['name']] = api('POST', path, entry)['id']
    return have


def ensure_monster(api: Api, bestiary_id: str) -> str:
    path = f'{GAME}/bestiaries/{bestiary_id}/monsters'
    found = find(api('GET', path, None), 'name', content.MONSTER['name'])
    return found['id'] if found else api('POST', path, content.MONSTER)['id']


def check_publishable(api: Api, path: str) -> None:
    """게시 점검. 걸리면 까닭을 싣고 멈춘다."""
    checked = api('GET', f'{path}/publish-check', None)
    if not checked.get('ready'):
        raise SeedError(f'게시 점검에 걸렸다({path}): {checked.get("problems")}')


def publish_scenario(api: Api, scenario_id: str) -> None:
    """점검하고, 지금의 내용을 판으로 굳히고, 그 판을 공개한다."""
    path = f'{GAME}/scenarios/{scenario_id}'
    check_publishable(api, path)
    version = api('POST', f'{path}/versions', {'note': 'VM 테스트'})
    api('PUT', f'{path}/listing/publication', {'version': version['number']})


def seed_scenario(api: Api) -> Made:
    """꺼진 등대. 이미 공개돼 있으면 건드리지 않는다. 있되 공개 전이면 게시만 한다."""
    found = find(api('GET', f'{GAME}/scenarios?limit=100', None), 'title', content.SCENARIO_TITLE)
    if found and found.get('published_at'):
        return Made('TRPG 시나리오', content.SCENARIO_TITLE, found['id'], 'kept')
    if found:
        publish_scenario(api, found['id'])
        return Made('TRPG 시나리오', content.SCENARIO_TITLE, found['id'], 'published')
    model = pick_model(api('GET', f'{GAME}/tables/narration-models', None))
    rulebook_id = ensure_asset(api, 'rulebooks', content.RULEBOOK_TITLE, content.RULEBOOK)
    lorebook_id = ensure_asset(api, 'lorebooks', content.LOREBOOK_TITLE, content.LOREBOOK)
    bestiary_id = ensure_asset(api, 'bestiaries', content.BESTIARY_TITLE, content.BESTIARY)
    ids = ensure_entries(api, lorebook_id)
    monster_id = ensure_monster(api, bestiary_id)
    body = content.scenario_body(rulebook_id, model, lorebook_id, bestiary_id, ids, monster_id)
    scenario = api('POST', f'{GAME}/scenarios', body)
    api('PATCH', f'{GAME}/scenarios/{scenario["id"]}/listing', content.LISTING)
    publish_scenario(api, scenario['id'])
    return Made('TRPG 시나리오', content.SCENARIO_TITLE, scenario['id'], 'created')


# --- chat 과 story(asset 서버) ---


def seed_asset_lorebook(api: Api) -> str:
    """asset 서버의 로어북. 없으면 만들고, 판이 없으면 게시한다(캐릭터와 세계관은 게시한 로어북만 붙인다)."""
    found = find(api('GET', f'{ASSET}/lorebooks?limit=100', None), 'name', content.ASSET_LOREBOOK_NAME)
    made = found or api('POST', f'{ASSET}/lorebooks', content.ASSET_LOREBOOK)
    if made.get('latest_version') is None:
        api('POST', f'{ASSET}/lorebooks/{made["id"]}/versions', {})
    return made['id']


def seed_work(api: Api, kind: str, label: str, name: str, body: dict) -> Made:
    """캐릭터나 세계관 하나. 이름으로 찾고 없으면 만든다. 공개로 두고, 공개한 판이 없으면 점검해 게시한다."""
    found = find(api('GET', f'{ASSET}/{kind}?limit=100', None), 'name', name)
    if found and found.get('latest_version') is not None and found.get('visibility') == 'public':
        return Made(label, name, found['id'], 'kept')
    made = found or api('POST', f'{ASSET}/{kind}', body)
    path = f'{ASSET}/{kind}/{made["id"]}'
    api('PATCH', path, {'visibility': 'public'})
    check_publishable(api, path)
    api('POST', f'{path}/versions', {})
    return Made(label, name, made['id'], 'published' if found else 'created')


def seed_works(api: Api) -> list[Made]:
    """하람, 무진, 소금 시장의 밤. 세계관은 게시한 캐릭터만 인물로 쓴다."""
    lorebook_id = seed_asset_lorebook(api)
    haram = seed_work(api, 'characters', 'chat 캐릭터', content.HARAM_NAME, content.haram_body(lorebook_id))
    mujin = seed_work(api, 'characters', 'chat 캐릭터', content.MUJIN_NAME, content.mujin_body(lorebook_id))
    world_body = content.world_body(lorebook_id, mujin.id, haram.id)
    world = seed_work(api, 'worlds', 'story 세계관', content.WORLD_NAME, world_body)
    return [haram, mujin, world]


# --- 모으고 찍기 ---

STATES = {'created': '새로 만들어 게시했다', 'published': '있던 것을 게시했다', 'kept': '이미 게시돼 있었다'}
PAGES = {
    'TRPG 시나리오': '/trpg/scenarios/{id}',
    'chat 캐릭터': '/chat/characters/{id}',
    'story 세계관': '/story/worlds/{id}',
}


def seed(api: Api) -> list[Made]:
    return [seed_scenario(api), *seed_works(api)]


def report(made: list[Made], site: str) -> str:
    lines = ['채웠다.', '']
    for one in made:
        lines.append(f'  {one.kind} {one.name}: {STATES[one.state]}')
        lines.append(f'    {site}{PAGES[one.kind].format(id=one.id)}')
    lines += ['', '페르소나(새내기 기자 윤)는 플레이어가 자기 계정으로 만든다(T4-2).']
    return '\n'.join(lines)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    site = args.site.rstrip('/')
    try:
        context = tls_context(site, args.insecure)
        token = mint_token(args.ssh, args.repo_dir, ensure_username(args.creator), args.password)
        made = seed(http_api(site, token, context))
    except SeedError as error:
        print(error, file=sys.stderr)
        return 1
    print(report(made, site))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
