# game-server/tests/test_map_narration.py

"""
서술에 맵이 들어간다(#218).

넷을 본다.
  - 한 일의 줄: 가기와 찾기의 결과, 서 있는 곳이 붙는다. 출구와 숨은 길은 붙지 않는다.
    가짜 서술자는 이 줄을 장면으로 그대로 내보낸다. 숨은 길이 여기 실리면 모두에게 새어 나간다.
  - 맵 절: 언어 모델의 프롬프트에만 있다. 장소마다 누가 섰는지, 아는 출구, 숨은 길(실마리로만).
    찾기로 길을 찾은 라운드에는 그 길의 이름을 쓰라는 다루는 법이 붙는다(narration-21).
  - 테이블에서: 닫힐 때 굳히는 각자 한 일에 위치와 출구와 숨은 길이 들어간다. 이 라운드에 찾은 길은 출구가 된다.
  - 맵이 없는 테이블과 옛 라운드: 위치가 없고 맵 절도 없다. 굳혀 둔 옛 문서도 읽힌다.
"""

from types import SimpleNamespace

from fastapi import FastAPI
from httpx import AsyncClient

from app.assets.scenarios.snapshot import Snapshot
from app.rounds.move_lines import describe_move
from app.rounds.moves import MapView, place_note
from app.rounds.narration_request import read_moves, to_search
from app.rounds.narrator import Move, NarrationRequest, PlaceNote, SearchNote, TravelNote
from app.rounds.prompt import FOUND_NOTE, MAP_NOTE, MAP_TITLE, map_line, map_lines, round_text
from app.tables import places
from tests import test_table_map as map_tables
from tests.test_map_actions import FOUND, SEARCHING, going, load_dice, play
from tests.test_scenario_map import GATE, SQUARE, map_document
from tests.test_table_items import ME, events_of
from tests.test_table_map import move, start_duo
from tests.test_whispers import RecordingNarrator

# 지도 테스트의 픽스처를 그대로 쓴다. 방장(기사), 함께 앉는 사람(약사), 장소 여섯이 든 로어북.
# 맵: 성문(시작)-광장 큰길, 광장→지하실 숨긴 한쪽 길, 성문-숲 안개 길, 오두막-숲 안개 길, 탑은 명소
me = map_tables.me
friend = map_tables.friend
lore = map_tables.lore

AT_SQUARE = PlaceNote(name='광장', exits=['성문'], hidden=['지하실'])


def request_of(*moves: Move) -> NarrationRequest:
    return NarrationRequest(round_number=2, scene='성문 앞이다.', moves=list(moves))


# --- 한 일의 줄 ---


def test_a_line_tells_where_a_character_went_and_stands():
    line = describe_move(
        Move(
            '기사',
            '숲으로 간다.',
            travel=TravelNote(from_place='성문', to_place='숲', moved=True),
            place=PlaceNote('숲'),
        )
    )

    assert line == '기사: 숲으로 간다. (간 곳: 성문 → 숲) [있는 곳: 숲]'


def test_a_line_tells_why_a_character_did_not_go():
    note = TravelNote(from_place='탑', to_place='광장', moved=False, reason='not_adjacent')

    assert describe_move(Move('기사', '광장으로 간다.', travel=note)) == (
        '기사: 광장으로 간다. (가려던 곳: 광장. 그쪽으로 이어진 길이 없었다)'
    )


def test_a_line_tells_what_a_search_found_or_that_it_found_nothing():
    found = describe_move(Move('약사', '벽을 두드린다.', search=SearchNote(place='광장', found=['지하실'])))
    nothing = describe_move(Move('약사', '벽을 두드린다.', search=SearchNote(place='광장', found=[])))

    # 찾은 길은 이제 아는 길이다. "숨은 길"이라 부르면 맵 절의 "숨은 길은 드러내지 마라"에 눌린다
    assert found == '약사: 벽을 두드린다. (찾기: 길을 찾아냈다. 지하실(으)로 이어진다)'
    # 숨긴 길이 없었는지, 있는데 못 찾았는지 말하지 않는다
    assert nothing == '약사: 벽을 두드린다. (찾기: 찾은 것이 없다)'


def test_a_line_never_carries_the_exits_or_the_hidden_routes():
    # 가짜 서술자는 이 줄을 장면으로 내보낸다. 숨은 길이 여기 실리면 모두에게 새어 나간다
    line = describe_move(Move('기사', '둘러본다.', place=AT_SQUARE))

    assert line == '기사: 둘러본다. [있는 곳: 광장]'


def test_a_search_names_the_far_end_from_either_side():
    # 광장에서 성문으로 내려가는 한쪽 길을 성문 쪽에서 찾았다. 길은 광장으로 이어진다
    route = {
        'from_place': {'entry_id': str(SQUARE), 'name': '광장'},
        'to_place': {'entry_id': str(GATE), 'name': '성문'},
        'two_way': False,
    }
    at_gate = {'search': {'place': {'entry_id': str(GATE), 'name': '성문'}, 'found': [route]}}
    at_square = {'search': {'place': {'entry_id': str(SQUARE), 'name': '광장'}, 'found': [route]}}

    assert to_search(SimpleNamespace(outcome=at_gate)) == SearchNote(place='성문', found=['광장'])
    assert to_search(SimpleNamespace(outcome=at_square)) == SearchNote(place='광장', found=['성문'])


def test_a_hidden_route_is_hinted_from_either_end():
    secret = {'from_place': str(SQUARE), 'to_place': str(GATE), 'visibility': 'hidden', 'find': {'ability': 'wis'}}
    snapshot = Snapshot.model_validate(map_document(start_place=str(GATE), routes=[secret]))
    known = places.Knowledge(seen=frozenset({GATE}), found=frozenset())
    table = SimpleNamespace(place_items=[])
    names = {GATE: '성문', SQUARE: '광장'}
    mapping = MapView(table, snapshot, places.known_map(snapshot, known), known, names, {})

    at_gate = place_note(mapping, SimpleNamespace(sheet=SimpleNamespace(place_id=GATE)))
    at_square = place_note(mapping, SimpleNamespace(sheet=SimpleNamespace(place_id=SQUARE)))

    # 한쪽 길의 도착점(성문)에서도 숨은 길의 실마리는 있다. 길 너머는 광장이다
    assert at_gate == PlaceNote(name='성문', exits=[], hidden=['광장'])
    assert at_square == PlaceNote(name='광장', exits=[], hidden=['성문'])


# --- 맵 절 ---


def test_the_map_gathers_characters_by_place_with_exits_and_hints():
    forest = PlaceNote(name='숲', exits=['성문', '오두막'])
    moves = [Move('기사', None, place=AT_SQUARE), Move('약사', None, place=forest), Move('영애', None, place=AT_SQUARE)]

    assert map_lines(moves) == [
        MAP_TITLE,
        MAP_NOTE,
        '- 광장(기사, 영애): 나가는 길: 성문. 숨은 길(플레이어는 모름, 실마리로만): 지하실',
        '- 숲(약사): 나가는 길: 성문, 오두막',
        '',
    ]


def test_the_rule_for_found_routes_comes_only_when_a_search_found_one():
    found = Move('약사', '벽을 두드린다.', search=SearchNote(place='광장', found=['지하실']))
    nothing = Move('약사', '벽을 두드린다.', search=SearchNote(place='광장', found=[]))

    assert FOUND_NOTE in round_text(request_of(Move('기사', '둘러본다.'), found))
    assert FOUND_NOTE not in round_text(request_of(nothing))
    assert FOUND_NOTE not in round_text(request_of(Move('기사', '둘러본다.', place=AT_SQUARE)))


def test_the_map_rule_keeps_only_the_listed_hidden_routes_secret():
    # 넓게 막으면 찾은 길까지 쓰지 않는다(narration-21). 숨은 길이 없는 곳에는 실마리를 만들지 않는다
    assert "'숨은 길'로 적힌 것만" in MAP_NOTE
    assert "'숨은 길'이 적히지 않은 장소에는 그런 실마리를 만들지 마라" in MAP_NOTE
    place = PlaceNote(name='광장', exits=['성문'], hidden=['지하실'])

    assert map_line('광장', ['기사'], place).endswith('숨은 길(플레이어는 모름, 실마리로만): 지하실')


def test_a_place_without_known_exits_says_so():
    assert map_lines([Move('기사', None, place=PlaceNote('탑'))])[2] == '- 탑(기사): 나가는 길: 없음'


def test_the_map_comes_after_the_quests_and_before_the_people_only_when_someone_stands_on_it():
    with_map = round_text(request_of(Move('기사', '둘러본다.', place=AT_SQUARE)))
    without = round_text(request_of(Move('기사', '둘러본다.')))

    assert MAP_TITLE in with_map
    assert with_map.index(MAP_TITLE) < with_map.index('[2 라운드에 한 일과 결과]')
    assert MAP_TITLE not in without


# --- 테이블에서 ---


async def test_the_narrator_gets_where_everyone_stands_and_what_lies_hidden(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore)
    await move(client, me, table, ME, lore['square'])
    recording = RecordingNarrator()
    app.state.narrator = recording

    await play(client, me, friend, table, narrated, theirs=going(lore['forest']))

    (request,) = recording.requests
    knight, apothecary = request.moves
    # 기사는 광장에 있다. 지하실로 가는 숨긴 길은 GM 만 안다
    assert knight.place == PlaceNote(name='광장', exits=['성문'], hidden=['지하실'])
    # 약사는 성문에서 숲으로 갔다. 숲에 서니 오두막으로 가는 안개 길이 보인다
    assert apothecary.travel == TravelNote(from_place='성문', to_place='숲', moved=True)
    assert apothecary.place == PlaceNote(name='숲', exits=['성문', '오두막'])


async def test_a_route_found_this_round_is_an_exit_not_a_secret(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore)
    await move(client, me, table, ME, lore['square'])
    recording = RecordingNarrator()
    app.state.narrator = recording
    load_dice(app, [FOUND])

    await play(client, me, friend, table, narrated, mine=SEARCHING)

    knight = recording.requests[0].moves[0]
    assert knight.search == SearchNote(place='광장', found=['지하실'])
    assert knight.place == PlaceNote(name='광장', exits=['성문', '지하실'])


async def test_the_plain_narration_never_names_a_hidden_place(
    client: AsyncClient, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore)
    await move(client, me, table, ME, lore['square'])

    # 가짜 서술자는 한 일의 줄을 그대로 장면으로 쓴다. 그 장면은 모두가 읽는다
    await play(client, me, friend, table, narrated)

    # 처음 장면(스타팅) 다음의 것이 이 라운드의 서술이다
    scene = (await events_of(client, friend, table, 'gm_narration'))[-1]
    assert '[있는 곳: 광장]' in scene['payload']['text']
    assert '지하실' not in scene['payload']['text']


async def test_a_table_without_a_map_has_no_places_in_the_narration(
    client: AsyncClient, app: FastAPI, me: dict, friend: dict, lore: dict, narrated
):
    table = await start_duo(client, me, friend, lore, start_place=None)
    recording = RecordingNarrator()
    app.state.narrator = recording

    await play(client, me, friend, table, narrated)

    assert [moved.place for moved in recording.requests[0].moves] == [None, None]
    assert MAP_TITLE not in round_text(recording.requests[0])


def test_moves_frozen_before_the_map_are_still_read():
    # 맵이 생기기 전에 닫기 시작한 라운드에 굳혀 둔 문서다. 위치와 가기, 찾기의 칸이 없다
    (old,) = read_moves([{'character_name': '기사', 'content': '달린다.'}])

    assert (old.place, old.travel, old.search) == (None, None, None)
