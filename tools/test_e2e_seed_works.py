# tools/test_e2e_seed_works.py

"""
종단간 테스트의 작품 채우기(e2e/seed_works.py)를 본다. 서버를 부르지 않는다. 보내는 본문과 이미 게시한 것을 넘기는지다.

    사용: python3 -m unittest discover -s tools -p 'test_e2e_seed_works.py'
"""

import tomllib
import unittest
from pathlib import Path
from unittest import mock

from e2e import seed_works, stub_llm

CATALOG = Path(__file__).resolve().parent / 'e2e' / 'local-models.toml'


class BodyTests(unittest.TestCase):
    def test_the_world_casts_the_character_at_the_start_place(self):
        body = seed_works.world_body('c-1')

        self.assertEqual(body['name'], seed_works.WORLD_NAME)
        self.assertEqual(body['start_place'], body['places'][0]['id'])
        self.assertEqual(body['cast'][0]['character_id'], 'c-1')
        self.assertEqual(body['cast'][0]['home'], body['start_place'])

    def test_the_cast_id_is_the_speaker_of_the_story_reply(self):
        cast_id = seed_works.world_body('c-1')['cast'][0]['id']

        self.assertIn(f'@{cast_id}:', stub_llm.STORY_REPLY)

    def test_the_character_has_a_start(self):
        body = seed_works.character_body()

        self.assertEqual(body['name'], seed_works.CHARACTER_NAME)
        self.assertEqual(body['starts'], [seed_works.START])


class PublishTests(unittest.TestCase):
    def test_a_published_public_work_is_left_alone(self):
        with mock.patch.object(seed_works, 'call') as call:
            seed_works.publish_public(
                'http://p', 't', 'worlds', {'id': 'w', 'latest_version': 1, 'visibility': 'public'}
            )

        call.assert_not_called()

    def test_a_new_work_is_made_public_then_published(self):
        with mock.patch.object(seed_works, 'call') as call:
            seed_works.publish_public(
                'http://p', 't', 'worlds', {'id': 'w', 'latest_version': None, 'visibility': 'private'}
            )

        self.assertEqual(
            [c.args[2:4] for c in call.call_args_list],
            [('PATCH', '/api/v1/asset/worlds/w'), ('POST', '/api/v1/asset/worlds/w/versions')],
        )

    def test_an_existing_work_is_not_made_again(self):
        found = {'id': 'c', 'latest_version': 1, 'visibility': 'public'}
        with (
            mock.patch.object(seed_works, 'find_mine', return_value=found),
            mock.patch.object(seed_works, 'call') as call,
        ):
            made = seed_works.seed_work('http://p', 't', 'characters', 'x', {})

        self.assertIs(made, found)
        call.assert_not_called()


class CatalogTests(unittest.TestCase):
    def test_every_stub_reply_has_a_model_in_the_catalog(self):
        # e2e.sh 가 켜는 이름표와 가짜 모델이 답을 고르는 이름(api_model_id)이 같아야 한다
        models = tomllib.loads(CATALOG.read_text(encoding='utf-8'))['models']

        self.assertEqual({model['api_model_id'] for model in models}, set(stub_llm.REPLIES))


if __name__ == '__main__':
    unittest.main()
