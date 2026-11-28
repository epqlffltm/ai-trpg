# trpg-server/tests/test_references_wiki_build.py

"""
위키백과로 데이터 파일을 만드는 명령(scripts/build_wiki.py)을 검증한다. 네트워크를 쓰지 않는다(httpx 의 가짜 전송).

보는 것.
  - User-Agent 에 도구의 이름과 연락처를 싣는다. 물을 때마다 쉰다
  - 서버가 바쁘다고 하면(429, 503, maxlag) Retry-After 만큼 쉬고 다시 묻는다. 계속 바쁘거나 틀린 답이면 멈춘다
  - 만든 결과의 줄(고칠 제목을 함께 적는다)
  - 명령줄. 받을 때는 연락처를 꼭 적는다. 생김새 글만 다시 붙일 때는 묻지 않는다
거르는 규칙과 차례는 공용 패키지의 시험이 본다(shared/reference-core/tests/test_wiki.py).
"""

from pathlib import Path

import httpx
import pytest
from reference_core.data import WIKIPEDIA_FILE, WIKIPEDIA_LOOKS_FILE, WIKIPEDIA_TRANSLATION_FILE
from reference_core.records import read_document
from reference_core.wiki_build import BuildReport

from scripts import build_wiki as script

PAGE = {'pageid': 1, 'title': '범선', 'extract': '돛으로 가는 배다.', 'revisions': [{'revid': 10}], 'fullurl': 'u'}


def client_of(*responses: httpx.Response, seen: list[httpx.Request] | None = None) -> httpx.Client:
    queue = list(responses)

    def answer(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return queue.pop(0)

    return httpx.Client(
        transport=httpx.MockTransport(answer), headers={'User-Agent': script.user_agent('me@example.com')}
    )


def ok(pages: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={'query': {'pages': pages}})


def test_the_question_carries_the_contact_and_pauses():
    seen: list[httpx.Request] = []
    pauses: list[float] = []
    fetch = script.make_fetch(client_of(ok([PAGE]), seen=seen), pause=1.5, sleep=pauses.append)

    answer = fetch('ko', ['범선'])

    assert answer['query']['pages'][0]['title'] == '범선'
    assert seen[0].headers['User-Agent'] == 'ai-trpg-reference-builder/1.0 (me@example.com)'
    assert seen[0].url.host == 'ko.wikipedia.org'
    assert seen[0].url.params['titles'] == '범선'
    assert pauses == [1.5]


def test_a_busy_server_is_asked_again_after_waiting():
    pauses: list[float] = []
    busy = httpx.Response(429, headers={'Retry-After': '7'})
    lagged = httpx.Response(200, json={'error': {'code': 'maxlag'}})
    unavailable = httpx.Response(503)
    fetch = script.make_fetch(client_of(busy, lagged, unavailable, ok([PAGE])), pause=0, sleep=pauses.append)

    answer = fetch('en', ['Carrack'])

    assert 'query' in answer
    assert pauses == [0, 7.0, 0, script.BUSY_SECONDS, 0, script.BUSY_SECONDS, 0]


def test_a_server_that_stays_busy_or_answers_wrong_stops_the_build():
    always_busy = [httpx.Response(503) for _ in range(script.RETRIES + 1)]
    with pytest.raises(script.WikiUnavailable, match='바쁘다'):
        script.make_fetch(client_of(*always_busy), pause=0, sleep=lambda _: None)('ko', ['범선'])
    with pytest.raises(script.WikiUnavailable, match='HTTP 403'):
        script.make_fetch(client_of(httpx.Response(403, text='no')), pause=0, sleep=lambda _: None)('ko', ['범선'])
    with pytest.raises(script.WikiUnavailable):
        script.make_fetch(
            client_of(httpx.Response(200, json={'error': {'code': 'badvalue'}})), pause=0, sleep=lambda _: None
        )('ko', ['범선'])


def test_the_report_lists_what_to_fix():
    report = BuildReport(
        written=3,
        english=['캐럭'],
        missing=['없는 배'],
        emptied=['코그선'],
        duplicated=['돛단배'],
        untranslated=['en/Carrack'],
        stale=['en/Gone'],
        unlooked=['ko/범선'],
        stale_looks=['ko/수정구'],
    )

    lines = script.describe(report, Path('wikipedia.json'))

    assert lines[0] == 'wikipedia.json: 3줄(영어판 1)'
    assert any('없는 배' in line for line in lines)
    assert any('코그선' in line for line in lines)
    assert any('돛단배' in line for line in lines)
    assert any('en/Carrack' in line and '번역이 없다' in line for line in lines)
    assert any('en/Gone' in line for line in lines)
    assert any('ko/범선' in line and '생김새 글이 없다' in line for line in lines)
    assert any('ko/수정구' in line and '생김새 글 파일에서 지운다' in line for line in lines)
    assert script.describe(BuildReport(written=1), Path('w.json')) == ['w.json: 1줄(영어판 0)']


def test_the_command_needs_a_contact():
    with pytest.raises(SystemExit):
        script.parse([])

    args = script.parse(['--contact', 'me@example.com'])

    assert (args.output, args.pause, args.translation) == (WIKIPEDIA_FILE, 1.0, WIKIPEDIA_TRANSLATION_FILE)
    assert (args.looks, args.looks_only) == (WIKIPEDIA_LOOKS_FILE, False)
    # 생김새 글만 붙일 때는 위키백과에 묻지 않으니 연락처가 없어도 된다
    assert script.parse(['--looks-only']).looks_only


def test_looks_only_refreshes_the_file_without_the_network(tmp_path: Path, capsys: pytest.CaptureFixture):
    output, looks = tmp_path / 'wikipedia.json', tmp_path / 'looks.json'
    output.write_text(WIKIPEDIA_FILE.read_text(encoding='utf-8'), encoding='utf-8')
    looks.write_text(WIKIPEDIA_LOOKS_FILE.read_text(encoding='utf-8'), encoding='utf-8')

    script.main(['--looks-only', '--output', str(output), '--looks', str(looks)])

    # 실린 파일은 이미 생김새 글을 붙인 것이라 다시 붙여도 같다
    assert output.read_text(encoding='utf-8') == WIKIPEDIA_FILE.read_text(encoding='utf-8')
    count = len(read_document(WIKIPEDIA_FILE).entries)
    assert f'{count}줄' in capsys.readouterr().out
