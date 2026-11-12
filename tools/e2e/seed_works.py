# tools/e2e/seed_works.py

"""
종단간 테스트(web/e2e)의 chat·story 흐름이 쓸 작품을 채운다.
공개된 캐릭터 하나와, 그 캐릭터가 나오는 공개된 세계관 하나다.
표준 라이브러리만 쓴다. 견본 계정(tools/dev_seed.py 의 seed_host)이 만들고 게시한다. asset 서버를 프록시를 거쳐 부른다.

캐릭터와 세계관을 만드는 것은 지금 운영자만이다. e2e 의 스택은 asset 서버에서 누구나 만들고 공개하게 연다
(docker-compose.e2e.yml 의 CHARACTERS_FOR_EVERYONE, PUBLIC_FOR_EVERYONE). 견본 계정을 운영자로 올리지 않는다.

몇 번 돌려도 같다. 이름으로 찾아 이미 게시한 것이 있으면 만들지 않는다.

    사용(저장소 루트에서, e2e 의 스택을 띄우고 dev_seed.py 를 돌린 뒤):
      python3 tools/e2e/seed_works.py --proxy http://127.0.0.1:8080 --password seed-pass-2026
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_seed import SeedError, call, ensure_local, seed_accounts  # noqa: E402

ASSET = '/api/v1/asset'
# 테스트가 화면에서 찾는 이름(web/e2e 의 support/works.ts 와 같다)
CHARACTER_NAME = '[e2e] 세라'
WORLD_NAME = '[e2e] 여름 학원'
START = {'title': '비 오는 밤', 'situation': '카페의 문을 두드리는 소리가 난다.'}
STAGES = [{'name': '낯섦', 'at': 0}, {'name': '친함', 'at': 40}]


def character_body() -> dict:
    """가장 작은 캐릭터. 시작 상황 하나와 말투."""
    return {
        'genre': 'romance',
        'name': CHARACTER_NAME,
        'intro_html': '<p>종단간 테스트의 캐릭터.</p>',
        'speech_examples': '조용히 웃으며 말한다.',
        'starts': [START],
    }


def world_body(character_id: str) -> dict:
    """가장 작은 세계관. 장소 하나와, 그 장소에 사는 인물(위의 캐릭터) 하나."""
    return {
        'genre': 'romance',
        'name': WORLD_NAME,
        'intro_html': '<p>종단간 테스트의 세계관.</p>',
        'places': [{'id': 'school', 'name': '학교'}],
        'start_place': 'school',
        'cast': [{'id': 'sera', 'character_id': character_id, 'home': 'school', 'affection': {'stages': STAGES}}],
    }


def find_mine(proxy: str, token: str, kind: str, name: str) -> dict | None:
    """자기 작품 가운데 그 이름의 것. 없으면 None."""
    page = call(proxy, token, 'GET', f'{ASSET}/{kind}?limit=100')
    return next((item for item in page.get('items', []) if item.get('name') == name), None)


def publish_public(proxy: str, token: str, kind: str, made: dict) -> None:
    """공개로 두고 게시한다. 이미 게시한 판이 있으면 넘어간다."""
    if made.get('latest_version') is not None and made.get('visibility') == 'public':
        return
    call(proxy, token, 'PATCH', f'{ASSET}/{kind}/{made["id"]}', {'visibility': 'public'})
    call(proxy, token, 'POST', f'{ASSET}/{kind}/{made["id"]}/versions', {})


def seed_work(proxy: str, token: str, kind: str, name: str, body: dict) -> dict:
    """그 작품을 찾거나 만들어 공개로 게시한다."""
    made = find_mine(proxy, token, kind, name) or call(proxy, token, 'POST', f'{ASSET}/{kind}', body)
    publish_public(proxy, token, kind, made)
    return made


def run(proxy: str, password: str) -> tuple[dict, dict]:
    ensure_local(proxy)
    host = seed_accounts(password)[0]
    character = seed_work(proxy, host.access_token, 'characters', CHARACTER_NAME, character_body())
    world = seed_work(proxy, host.access_token, 'worlds', WORLD_NAME, world_body(character['id']))
    return character, world


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='e2e 의 chat·story 흐름이 쓸 공개 캐릭터와 세계관을 채운다')
    parser.add_argument('--proxy', default='http://127.0.0.1:8080', help='프록시의 주소')
    parser.add_argument('--password', required=True, help='견본 계정의 비밀번호(dev_seed.py 와 같게)')
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        character, world = run(args.proxy.rstrip('/'), args.password)
    except SeedError as error:
        print(error, file=sys.stderr)
        return 1
    print(f'캐릭터: {character["id"]} {CHARACTER_NAME}')
    print(f'세계관: {world["id"]} {WORLD_NAME}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
