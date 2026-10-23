# asset-server/app/characters/publishing.py

"""
캐릭터를 게시할 수 있는지 보는 규칙과, 게시할 때 소개를 거르는 것(#567). DB 를 모르는 순수한 함수다.

막는 것(problems)과 알리는 것(removed)을 나눈다.
  - 막는 것: 이것이 없으면 대화를 시작할 수 없거나, 지도와 물건이 서로 맞지 않거나, 남의 그림을 쓴다.
    게시가 409 로 돌려준다.
    초안은 고치는 중이라 어긋날 수 있다(장소를 지웠는데 길이 남았다). 판에는 맞는 것만 들어간다.
    그림이 자기 것인지는 DB 를 봐야 알아서 서비스가 본다(app/characters/service.py 의 publishing_problems).
  - 알리는 것: 소개에서 걸러 낸 태그, 속성, CSS, 링크, 그림. 게시는 되고, 거른 소개가 판에 들어간다.
나이와 성별로 막는 검사는 없다(2026-10-21).
"""

import enum
import uuid
from collections.abc import Mapping, Sequence

from app.characters.documents import LorebookCopyDocument, lorebook_copy
from app.characters.models import Character, ItemKind, SceneWhen, TriggerKind
from app.content.html import Cleaned, clean_intro, image_ids


class Problem(enum.StrEnum):
    """게시할 수 없는 이유."""

    # 시작 상황이 하나도 없다. 대화는 시작 상황을 고르고 들어간다
    START_MISSING = 'start_missing'
    # 대표 그림이나 소개 글, 장소, 물건의 그림 가운데 자기가 올린 것이 아닌(또는 없는) 그림이 있다
    IMAGE_NOT_OWNED = 'image_not_owned'
    # 길이나 처음 있는 장소가 없는 장소를 가리킨다
    PLACE_MISSING = 'place_missing'
    # 장소가 있는데 처음 있는 장소를 고르지 않았다. 대화가 어디서 시작하는지 모른다
    START_PLACE_MISSING = 'start_place_missing'
    # 시작 소지품이 없는 물건을 가리킨다
    ITEM_MISSING = 'item_missing'
    # 호감도의 규칙이 없는 물건이나 장소를 가리킨다
    AFFECTION_TARGET_MISSING = 'affection_target_missing'
    # 이벤트 씬의 조건이 없는 장소나 물건, 호감도의 단계를 가리킨다(호감도가 없는데 단계를 가리키는 것도)
    SCENE_TARGET_MISSING = 'scene_target_missing'
    # 캐릭터 그림의 차림이 없는 물건이나 옷이 아닌 물건을 가리킨다
    SPRITE_OUTFIT_MISSING = 'sprite_outfit_missing'
    # 가리킨 로어북이 없다(지웠다)
    LOREBOOK_MISSING = 'lorebook_missing'
    # 가리킨 로어북을 게시한 적이 없다. 판에 복사할 것이 없다
    LOREBOOK_UNPUBLISHED = 'lorebook_unpublished'


class CharacterNotReadyError(Exception):
    """게시할 조건을 갖추지 못했다. problems 는 갖추지 못한 것 전부다(한 번에 알린다)."""

    def __init__(self, problems: list[Problem]) -> None:
        super().__init__(', '.join(problems))
        self.problems = problems


def place_problems(character: Character) -> list[Problem]:
    """
    지도가 맞지 않는 것들. 길의 양쪽과 처음 있는 장소는 있는 장소여야 한다.
    장소가 있으면 처음 있는 장소가 있어야 한다.
    """
    known = {place['id'] for place in character.places}
    pointed = [end for path in character.paths for end in (path['a'], path['b'])]
    if character.start_place is not None:
        pointed.append(character.start_place)
    problems = [Problem.PLACE_MISSING] if any(place not in known for place in pointed) else []
    if known and character.start_place is None:
        problems.append(Problem.START_PLACE_MISSING)
    return problems


def item_problems(character: Character) -> list[Problem]:
    """물건이 맞지 않는 것들. 시작 소지품은 있는 물건이어야 한다."""
    known = {item['id'] for item in character.items}
    return [Problem.ITEM_MISSING] if any(start['item'] not in known for start in character.start_items) else []


def affection_problems(character: Character) -> list[Problem]:
    """호감도가 맞지 않는 것들. 규칙의 대상은 있는 물건(건넸다, 썼다)이나 장소(갔다)여야 한다."""
    if not character.affection:
        return []
    places = {place['id'] for place in character.places}
    items = {item['id'] for item in character.items}
    for rule in character.affection['rules']:
        known = places if rule['on']['kind'] == TriggerKind.REACH_PLACE else items
        if rule['on']['target'] not in known:
            return [Problem.AFFECTION_TARGET_MISSING]
    return []


def scene_targets(character: Character) -> dict[str, set[str]]:
    """이벤트 씬의 조건이 가리킬 수 있는 것들. 조건의 종류마다 장소의 id, 물건의 id, 호감도 단계의 이름이다."""
    stages = {stage['name'] for stage in character.affection['stages']} if character.affection else set()
    return {
        SceneWhen.REACH_PLACE: {place['id'] for place in character.places},
        SceneWhen.GIVE_ITEM: {item['id'] for item in character.items},
        SceneWhen.AFFECTION_STAGE: stages,
    }


def scene_problems(character: Character) -> list[Problem]:
    """이벤트 씬이 맞지 않는 것들. 조건은 있는 장소, 물건, 호감도의 단계를 가리켜야 한다."""
    known = scene_targets(character)
    for scene in character.event_scenes:
        when = scene['when']
        if when['target'] not in known[when['kind']]:
            return [Problem.SCENE_TARGET_MISSING]
    return []


def sprite_problems(character: Character) -> list[Problem]:
    """캐릭터 그림이 맞지 않는 것들. 차림은 있는 옷(물건의 종류가 clothing)이어야 한다."""
    clothes = {item['id'] for item in character.items if item.get('kind') == ItemKind.CLOTHING}
    outfits = [sprite['outfit'] for sprite in character.sprites if sprite.get('outfit') is not None]
    return [Problem.SPRITE_OUTFIT_MISSING] if any(outfit not in clothes for outfit in outfits) else []


def find_problems(character: Character) -> list[Problem]:
    """게시를 막는 것들. 없으면 빈 목록이다."""
    problems = [] if character.starts else [Problem.START_MISSING]
    problems += place_problems(character) + item_problems(character)
    return problems + affection_problems(character) + scene_problems(character) + sprite_problems(character)


def lorebook_copies(
    lorebook_ids: Sequence[uuid.UUID], found: Mapping[uuid.UUID, int | None], documents: Mapping[uuid.UUID, dict]
) -> tuple[list[LorebookCopyDocument], list[Problem]]:
    """
    가리킨 로어북들(차례대로)을 판에 넣을 것과 막는 것들로 가른다.
    found 는 자기 로어북의 마지막 판 번호(게시한 적이 없으면 None), documents 는 그 판의 문서다.
    found 에 없으면 지운(또는 남의) 로어북이다.
    """
    copies: list[LorebookCopyDocument] = []
    problems: list[Problem] = []
    for lorebook_id in lorebook_ids:
        if lorebook_id not in found:
            problems.append(Problem.LOREBOOK_MISSING)
        elif found[lorebook_id] is None:
            problems.append(Problem.LOREBOOK_UNPUBLISHED)
        else:
            copies.append(lorebook_copy(lorebook_id, found[lorebook_id], documents[lorebook_id]))
    return copies, list(dict.fromkeys(problems))


def cleaned_intro(character: Character) -> Cleaned:
    """초안의 소개를 거른 것과 걸러 낸 것들."""
    return clean_intro(character.intro_html)


def world_image_ids(character: Character) -> list[uuid.UUID]:
    """장소의 배경(기본과 시간대마다), 물건의 그림, 이벤트 씬, 캐릭터 그림. 초안에는 글로 적혀 있다."""
    entries = [*character.places, *character.items, *character.event_scenes, *character.sprites]
    found = [uuid.UUID(entry['image_id']) for entry in entries if entry.get('image_id')]
    backgrounds = [image for place in character.places for image in place.get('backgrounds', {}).values()]
    return found + [uuid.UUID(image) for image in backgrounds]


def used_image_ids(character: Character, intro_html: str) -> list[uuid.UUID]:
    """
    판에 쓰이는 그림들. 대표 그림, 거른 소개 글의 그림, 장소와 물건의 그림이다.
    처음 나온 차례로, 같은 것은 한 번만이다.
    """
    found = [character.image_id] if character.image_id else []
    return list(dict.fromkeys([*found, *image_ids(intro_html), *world_image_ids(character)]))
