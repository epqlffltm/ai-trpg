# chat-server/tests/test_world_sprites.py

"""
지금 띄울 캐릭터 그림을 고르는 것(app/world/sprites.py)을 검증한다. DB 를 쓰지 않는다.

보는 것.
  - 처음 차림이면 처음 차림의 기본 표정 그림이다
  - 상대가 옷을 입으면 그 차림의 그림이다. 여럿을 입었으면 가장 나중에 입은 것부터, 그림이 있는 차림이다
  - 기본 표정의 그림이 없으면 그 차림의 첫 그림이다
  - 맞는 그림이 하나도 없으면 없다
"""

import uuid
from dataclasses import replace

from app.world.sprites import current_sprite, sprite_image
from app.world.state import initial_state
from tests.assets import make_character


def picture(number: int) -> str:
    return str(uuid.UUID(int=number))


ITEMS = [
    {'id': 'scarf', 'name': '목도리', 'description': '', 'kind': 'clothing', 'image_id': None},
    {'id': 'coat', 'name': '외투', 'description': '', 'kind': 'clothing', 'image_id': None},
    {'id': 'hat', 'name': '모자', 'description': '', 'kind': 'clothing', 'image_id': None},
]
SPRITES = [
    {'id': 'smile', 'image_id': picture(1), 'expression': '웃음', 'outfit': None},
    {'id': 'base', 'image_id': picture(2), 'expression': '', 'outfit': None},
    {'id': 'scarf', 'image_id': picture(3), 'expression': '', 'outfit': 'scarf'},
    {'id': 'coat-smile', 'image_id': picture(4), 'expression': '웃음', 'outfit': 'coat'},
]
DOCUMENT = make_character(world={'items': ITEMS, 'sprites': SPRITES}).document
START = initial_state(DOCUMENT)


def test_the_first_outfit_shows_its_base_expression():
    assert current_sprite(DOCUMENT, START).id == 'base'
    assert sprite_image(DOCUMENT, START) == uuid.UUID(picture(2))


def test_a_worn_garment_shows_its_sprite():
    assert current_sprite(DOCUMENT, replace(START, outfit=('scarf',))).id == 'scarf'


def test_the_latest_garment_with_a_sprite_wins():
    # 모자는 그림이 없어 건너뛰고, 외투보다 나중에 입은 목도리의 그림이다
    assert current_sprite(DOCUMENT, replace(START, outfit=('coat', 'scarf', 'hat'))).id == 'scarf'
    assert current_sprite(DOCUMENT, replace(START, outfit=('scarf', 'coat'))).id == 'coat-smile'


def test_without_a_base_expression_the_first_sprite_of_that_outfit_is_used():
    assert current_sprite(DOCUMENT, replace(START, outfit=('coat',))).id == 'coat-smile'


def test_a_garment_without_sprites_falls_back_to_the_first_outfit():
    assert current_sprite(DOCUMENT, replace(START, outfit=('hat',))).id == 'base'


def test_no_sprites_means_none():
    bare = make_character(world={'items': ITEMS}).document
    only_dressed = make_character(world={'items': ITEMS, 'sprites': SPRITES[2:]}).document

    assert sprite_image(bare, initial_state(bare)) is None
    assert current_sprite(only_dressed, initial_state(only_dressed)) is None
