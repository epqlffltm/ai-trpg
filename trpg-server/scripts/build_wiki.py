# trpg-server/scripts/build_wiki.py

"""
위키백과의 문서로 참고 자료의 데이터 파일(reference_core/data/wikipedia.json)을 만든다. 개발자가 자기 PC 에서 쓴다.

제목 목록(reference_core/data/wikipedia-titles.txt)의 문서를 MediaWiki API 로 받아 도입부를 거른다.
한국어판 먼저, 없으면 영어판이다. 차례와 거르는 규칙은 reference_core/wiki_build.py 와 reference_core/wiki.py 다.
영어판의 줄은 번역 파일(reference_core/data/wikipedia.ko.json)이 있으면 붙인다. 번역이 없는 줄은 끝에 알린다.
모든 줄에 생김새 글 파일(reference_core/data/wikipedia.looks.json)이 있으면 붙인다. 생김새 글이 없는 줄도 알린다.
여기는 HTTP 로 묻는 것만 한다. 운영 서버는 위키백과를 부르지 않고 만든 파일을 넣는다(scripts/references.py load).

    uv run python -m scripts.build_wiki --contact you@example.com
    uv run python -m scripts.build_wiki --looks-only   # 생김새 글만 고쳤을 때. 위키백과에 묻지 않는다

위키미디어의 API 이용 규칙을 따른다.
  - User-Agent 에 이 도구의 이름과 연락처를 적는다(--contact, 메일이나 주소). 없으면 막힐 수 있다
  - 한 번에 하나씩, 묻는 사이에 쉰다(--pause, 기본 1초). 제목 20개를 한 번에 묻는다
  - 서버가 바쁘다고 하면(maxlag, 429, 503) Retry-After 만큼 쉬고 다시 묻는다(RETRIES 번)
trpg-server 폴더에서 -m 으로 돌린다. DB 와 설정은 쓰지 않는다. 기본으로 만드는 곳은 저장소 안의 공용 패키지 폴더다.
"""

import argparse
import time
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from reference_core.data import (
    WIKIPEDIA_FILE,
    WIKIPEDIA_LOOKS_FILE,
    WIKIPEDIA_PLACES_FILE,
    WIKIPEDIA_TITLES_FILE,
    WIKIPEDIA_TRANSLATION_FILE,
)
from reference_core.wiki_api import API_URLS, query_params
from reference_core.wiki_build import BuildReport, Fetch, build, refresh_looks

# 도구의 이름(User-Agent 의 앞)
TOOL = 'ai-trpg-reference-builder/1.0'
# 서버가 바쁘다고 할 때 다시 묻는 횟수와, Retry-After 가 없을 때 쉬는 초
RETRIES = 3
BUSY_SECONDS = 5.0
# 기다리는 시간의 상한(초). 오래 걸리면 실패로 본다
TIMEOUT_SECONDS = 30.0
BUSY_STATUSES = frozenset({429, 503})


class WikiUnavailable(Exception):
    """위키백과가 답하지 않는다(다시 물어도 바쁘다, 틀린 답)."""


def user_agent(contact: str) -> str:
    """이 도구의 User-Agent. 위키미디어가 연락할 곳을 적는다."""
    return f'{TOOL} ({contact})'


def busy_seconds(response: httpx.Response, answer: Mapping[str, Any] | None) -> float | None:
    """서버가 바쁘다고 했으면 쉴 초, 아니면 None. 바쁜 답은 429, 503 이거나 maxlag 오류다."""
    lagged = answer is not None and answer.get('error', {}).get('code') == 'maxlag'
    if response.status_code not in BUSY_STATUSES and not lagged:
        return None
    retry_after = response.headers.get('Retry-After', '')
    return float(retry_after) if retry_after.isdigit() else BUSY_SECONDS


def answer_of(response: httpx.Response) -> Mapping[str, Any] | None:
    """답의 JSON. JSON 이 아니면 None 이다."""
    try:
        return response.json()
    except ValueError:
        return None


def make_fetch(client: httpx.Client, pause: float, sleep: Callable[[float], None] = time.sleep) -> Fetch:
    """
    언어판과 제목들을 받아 API 의 답을 돌려주는 것(reference_core/wiki_build.py 의 Fetch). 물을 때마다 pause 초 쉰다.
    sleep 은 시험이 바꿔 끼운다(실제로 쉬지 않게).
    """

    def fetch(lang: str, titles: list[str]) -> Mapping[str, Any]:
        for _ in range(RETRIES + 1):
            sleep(pause)
            response = client.get(API_URLS[lang], params=query_params(titles))
            answer = answer_of(response)
            wait = busy_seconds(response, answer)
            if wait is not None:
                sleep(wait)
                continue
            if response.is_error or answer is None or 'error' in answer:
                raise WikiUnavailable(f'{lang} 위키백과가 답하지 않았다(HTTP {response.status_code})')
            return answer
        raise WikiUnavailable(f'{lang} 위키백과가 {RETRIES}번 다시 물어도 바쁘다')

    return fetch


def describe(report: BuildReport, output: Path) -> list[str]:
    """만든 결과를 찍을 줄들. 고칠 제목(없음, 남은 글 없음, 겹침)을 함께 적는다."""
    lines = [f'{output}: {report.written}줄(영어판 {len(report.english)})']
    for label, titles in (
        ('한국어판과 영어판에 모두 없다(제목을 고치거나 지운다)', report.missing),
        ('거르고 남은 글이 없다', report.emptied),
        ('다른 제목과 같은 문서다(앞의 것만 넣었다)', report.duplicated),
        ('영어판인데 번역이 없다(번역 파일에 더한다)', report.untranslated),
        ('자료에 없는 줄의 번역이다(번역 파일에서 지운다)', report.stale),
        ('생김새 글이 없다(생김새 글 파일에 더한다)', report.unlooked),
        ('자료에 없는 줄의 생김새 글이다(생김새 글 파일에서 지운다)', report.stale_looks),
    ):
        if titles:
            lines.append(f'{label}: {", ".join(titles)}')
    return lines


def build_parser() -> argparse.ArgumentParser:
    """명령줄의 모양."""
    parser = argparse.ArgumentParser(description='위키백과의 문서로 참고 자료의 데이터 파일을 만든다.')
    parser.add_argument(
        '--contact', help='User-Agent 에 적을 연락처(메일이나 주소). 위키미디어의 규칙이다. 받을 때는 꼭 적는다'
    )
    parser.add_argument(
        '--looks-only',
        action='store_true',
        help='받지 않고, 만든 파일(--output)에 생김새 글(--looks)만 다시 붙인다',
    )
    parser.add_argument(
        '--titles', type=Path, default=WIKIPEDIA_TITLES_FILE, help=f'제목 목록. 기본 {WIKIPEDIA_TITLES_FILE}'
    )
    parser.add_argument(
        '--places',
        type=Path,
        default=WIKIPEDIA_PLACES_FILE,
        help=f'거를 나라·도시의 이름. 기본 {WIKIPEDIA_PLACES_FILE}',
    )
    parser.add_argument('--output', type=Path, default=WIKIPEDIA_FILE, help=f'만들 파일. 기본 {WIKIPEDIA_FILE}')
    parser.add_argument(
        '--translation',
        type=Path,
        default=WIKIPEDIA_TRANSLATION_FILE,
        help=f'영어판의 줄의 한국어 번역. 파일이 없으면 붙이지 않는다. 기본 {WIKIPEDIA_TRANSLATION_FILE}',
    )
    parser.add_argument(
        '--looks',
        type=Path,
        default=WIKIPEDIA_LOOKS_FILE,
        help=f'줄마다의 생김새 글. 파일이 없으면 붙이지 않는다. 기본 {WIKIPEDIA_LOOKS_FILE}',
    )
    parser.add_argument('--pause', type=float, default=1.0, help='묻는 사이에 쉬는 초. 기본 1')
    return parser


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    """명령줄을 읽는다. 받을 때는 연락처가 있어야 한다(생김새 글만 붙일 때는 묻지 않으니 없어도 된다)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.looks_only and not args.contact:
        parser.error('위키백과에서 받으려면 --contact 를 적어야 한다')
    return args


def fetched(args: argparse.Namespace) -> BuildReport:
    """위키백과에서 받아 데이터 파일을 만든다."""
    headers = {'User-Agent': user_agent(args.contact)}
    with httpx.Client(headers=headers, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
        fetch = make_fetch(client, args.pause)
        return build(
            args.titles, args.places, args.output, fetch, date.today().isoformat(), args.translation, args.looks
        )


def main(argv: list[str] | None = None) -> None:
    """명령줄을 읽고 돌린다."""
    args = parse(argv)
    report = refresh_looks(args.output, args.looks) if args.looks_only else fetched(args)
    for line in describe(report, args.output):
        print(line)


if __name__ == '__main__':
    main()
