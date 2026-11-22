# tools/test_vm_seed.py

"""
VM 에 테스트 작품을 채우는 스크립트(vm_seed.py)와 그 값(vm_seed_content.py)을 본다. VM 과 서버를 부르지 않는다.
서버는 가짜(FakeApi)로, SSH 는 subprocess 를 가짜로 바꾼다.

    사용: python3 -m unittest discover -s tools -p 'test_*.py'

인증 서버의 컨테이너에서 도는 vm_seed_token.py 는 Django 가 있어야 해서 여기서 부르지 않는다.
"""

import json
import ssl
import subprocess
import unittest
from unittest import mock

import vm_seed
import vm_seed_content as content
from vm_seed import (
    ASSET,
    GAME,
    RESULT_PREFIX,
    Made,
    SeedError,
    ensure_username,
    parse_token,
    pick_model,
    report,
    seed_scenario,
    seed_works,
    tls_context,
    token_command,
)

IDS = {entry['name']: f'e{index}' for index, entry in enumerate(content.ENTRIES)}
SCENARIOS = f'{GAME}/scenarios'


class FakeApi:
    """
    서버의 흉내. (방법, 주소) 마다 답을 정하고 받은 요청을 적는다. 정하지 않은 것은 시험을 실패시킨다.
    답이 부를 수 있는 것이면 본문을 넘겨 부른다(만들 때마다 다른 ID)
    """

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, body: dict | None = None):
        self.calls.append((method, path, body))
        answer = self.answers[(method, path)]
        return answer(body) if callable(answer) else answer

    def paths(self, method: str) -> list[str]:
        return [path for called, path, _ in self.calls if called == method]

    def body(self, method: str, path: str) -> dict | None:
        return next(body for called, at, body in self.calls if (called, at) == (method, path))


def new_ids(prefix: str):
    """만들 때마다 prefix-1, prefix-2 … 를 돌려주는 답"""
    counter = iter(range(1, 1000))
    return lambda body: {'id': f'{prefix}-{next(counter)}', **(body or {})}


def empty_game() -> dict:
    """아무것도 없는 게임 서버. 만들면 새 ID 를 준다. 점검은 통과한다"""
    return {
        ('GET', f'{SCENARIOS}?limit=100'): {'items': []},
        ('GET', f'{GAME}/tables/narration-models'): {'models': [{'slug': 'other'}, {'slug': 'gemma4-26b-a4b'}]},
        ('GET', f'{GAME}/rulebooks?limit=100'): {'items': []},
        ('POST', f'{GAME}/rulebooks'): {'id': 'r1'},
        ('GET', f'{GAME}/lorebooks?limit=100'): {'items': []},
        ('POST', f'{GAME}/lorebooks'): {'id': 'l1'},
        ('GET', f'{GAME}/bestiaries?limit=100'): {'items': []},
        ('POST', f'{GAME}/bestiaries'): {'id': 'b1'},
        ('GET', f'{GAME}/lorebooks/l1/entries'): [],
        ('POST', f'{GAME}/lorebooks/l1/entries'): lambda body: {'id': IDS[body['name']]},
        ('GET', f'{GAME}/bestiaries/b1/monsters'): [],
        ('POST', f'{GAME}/bestiaries/b1/monsters'): {'id': 'm1'},
        ('POST', SCENARIOS): {'id': 's1'},
        ('PATCH', f'{SCENARIOS}/s1/listing'): {},
        ('GET', f'{SCENARIOS}/s1/publish-check'): {'ready': True, 'problems': []},
        ('POST', f'{SCENARIOS}/s1/versions'): {'number': 1},
        ('PUT', f'{SCENARIOS}/s1/listing/publication'): {},
    }


class ArgumentsTest(unittest.TestCase):
    def test_only_usernames_of_the_auth_rules(self):
        self.assertEqual(ensure_username('op_a1'), 'op_a1')
        for bad in ('ab', 'Admin', 'a; rm -rf /', 'a b c d', 'x' * 21):
            with self.assertRaises(SeedError):
                ensure_username(bad)

    def test_insecure_only_for_test_hosts(self):
        self.assertIsNone(tls_context('https://staging.ai-trpg.test', insecure=False))
        context = tls_context('https://staging.ai-trpg.test', insecure=True)
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        with self.assertRaises(SeedError):
            tls_context('https://staging.example.com', insecure=True)


class TokenTest(unittest.TestCase):
    def test_sends_the_script_to_the_auth_container_over_ssh(self):
        command = token_command('trpg@vm.test', '/srv/ai-trpg', 'op_a1')
        self.assertEqual(command[:3], ['ssh', '-o', 'BatchMode=yes'])
        self.assertEqual(command[3], 'trpg@vm.test')
        self.assertEqual(
            command[4], 'cd /srv/ai-trpg && docker compose exec -T -e SEED_CREATOR=op_a1 auth-server python -'
        )

    def test_reads_the_last_token_line_and_skips_other_output(self):
        old, new = json.dumps({'access_token': 'old'}), json.dumps({'access_token': 't1'})
        output = f'경고 한 줄\n{RESULT_PREFIX}{old}\n{RESULT_PREFIX}{new}\n'
        self.assertEqual(parse_token(output), 't1')
        with self.assertRaises(SeedError):
            parse_token('운영자가 아니다: op_a1')

    def test_password_mode_lets_ssh_ask_for_the_password(self):
        command = token_command('trpg@vm.test', '/srv/ai-trpg', 'op_a1', ask_password=True)
        self.assertEqual(command[:2], ['ssh', 'trpg@vm.test'])
        self.assertNotIn('BatchMode=yes', command)

    def test_password_mode_leaves_stderr_on_the_screen(self):
        stdout = f'{RESULT_PREFIX}{{"access_token": "t1"}}'.encode()
        done = subprocess.CompletedProcess([], 0, stdout=stdout, stderr=None)
        with mock.patch.object(vm_seed.subprocess, 'run', return_value=done) as run:
            self.assertEqual(vm_seed.mint_token('trpg@vm.test', '/srv/ai-trpg', 'op_a1', ask_password=True), 't1')
        self.assertIsNone(run.call_args.kwargs['stderr'])
        self.assertEqual(run.call_args.kwargs['stdout'], subprocess.PIPE)

    def test_a_failed_password_login_is_an_error(self):
        done = subprocess.CompletedProcess([], 255, stdout=b'', stderr=None)
        with (
            mock.patch.object(vm_seed.subprocess, 'run', return_value=done),
            self.assertRaisesRegex(SeedError, '토큰을 받지 못했다'),
        ):
            vm_seed.mint_token('trpg@vm.test', '/srv/ai-trpg', 'op_a1', ask_password=True)

    def test_the_script_goes_on_stdin(self):
        stdout = f'{RESULT_PREFIX}{{"access_token": "t1"}}'.encode()
        done = subprocess.CompletedProcess([], 0, stdout=stdout, stderr=b'')
        with mock.patch.object(vm_seed.subprocess, 'run', return_value=done) as run:
            self.assertEqual(vm_seed.mint_token('trpg@vm.test', '/srv/ai-trpg', 'op_a1'), 't1')
        self.assertIn(b'issue_token_pair', run.call_args.kwargs['input'])

    def test_a_refusal_in_the_container_is_an_error(self):
        done = subprocess.CompletedProcess([], 1, stdout=b'', stderr='운영자가 아니다: op_a1'.encode())
        with (
            mock.patch.object(vm_seed.subprocess, 'run', return_value=done),
            self.assertRaisesRegex(SeedError, '운영자가 아니다'),
        ):
            vm_seed.mint_token('trpg@vm.test', '/srv/ai-trpg', 'op_a1')


class ModelTest(unittest.TestCase):
    def test_prefers_the_local_model(self):
        self.assertEqual(pick_model({'models': [{'slug': 'a'}, {'slug': 'gemma4-26b-a4b'}]}), 'gemma4-26b-a4b')
        self.assertEqual(pick_model({'models': [{'slug': 'a'}]}), 'a')
        with self.assertRaises(SeedError):
            pick_model({'models': []})


class ScenarioTest(unittest.TestCase):
    def test_makes_everything_then_checks_and_publishes(self):
        api = FakeApi(empty_game())

        made = seed_scenario(api)

        self.assertEqual(made, Made('TRPG 시나리오', content.SCENARIO_TITLE, 's1', 'created'))
        self.assertEqual(api.paths('POST').count(f'{GAME}/lorebooks/l1/entries'), len(content.ENTRIES))
        body = api.body('POST', SCENARIOS)
        self.assertEqual(body['narration_model'], 'gemma4-26b-a4b')
        self.assertEqual((body['rulebook_id'], body['lorebook_ids'], body['bestiary_ids']), ('r1', ['l1'], ['b1']))
        self.assertEqual(body['monster_sheets'][0]['monster_id'], 'm1')
        self.assertEqual(api.body('PATCH', f'{SCENARIOS}/s1/listing'), content.LISTING)
        self.assertEqual(api.body('PUT', f'{SCENARIOS}/s1/listing/publication'), {'version': 1})

    def test_existing_lorebook_entries_are_not_made_again(self):
        answers = empty_game()
        answers[('GET', f'{GAME}/lorebooks?limit=100')] = {'items': [{'id': 'l1', 'title': content.LOREBOOK_TITLE}]}
        answers[('GET', f'{GAME}/lorebooks/l1/entries')] = [{'id': IDS['부두'], 'name': '부두'}]
        api = FakeApi(answers)

        seed_scenario(api)

        self.assertNotIn(('POST', f'{GAME}/lorebooks'), [(m, p) for m, p, _ in api.calls])
        made = [body['name'] for method, path, body in api.calls if path.endswith('/entries') and method == 'POST']
        self.assertNotIn('부두', made)
        self.assertEqual(len(made), len(content.ENTRIES) - 1)

    def test_a_published_scenario_is_kept(self):
        found = {'id': 's9', 'title': content.SCENARIO_TITLE, 'published_at': '2026-11-17T00:00:00Z'}
        api = FakeApi({('GET', f'{SCENARIOS}?limit=100'): {'items': [found]}})

        self.assertEqual(seed_scenario(api).state, 'kept')
        self.assertEqual(api.paths('POST'), [])

    def test_an_unpublished_one_is_only_published(self):
        answers = empty_game()
        answers[('GET', f'{SCENARIOS}?limit=100')] = {'items': [{'id': 's1', 'title': content.SCENARIO_TITLE}]}
        api = FakeApi(answers)

        self.assertEqual(seed_scenario(api).state, 'published')
        self.assertEqual(api.paths('POST'), [f'{SCENARIOS}/s1/versions'])

    def test_stops_with_the_problems_when_the_check_fails(self):
        answers = empty_game()
        answers[('GET', f'{SCENARIOS}/s1/publish-check')] = {'ready': False, 'problems': ['quest_unreachable']}
        api = FakeApi(answers)

        with self.assertRaisesRegex(SeedError, 'quest_unreachable'):
            seed_scenario(api)
        self.assertNotIn(f'{SCENARIOS}/s1/versions', api.paths('POST'))


def empty_asset() -> dict:
    return {
        ('GET', f'{ASSET}/lorebooks?limit=100'): {'items': []},
        ('POST', f'{ASSET}/lorebooks'): {'id': 'al1', 'latest_version': None},
        ('POST', f'{ASSET}/lorebooks/al1/versions'): {'number': 1},
        ('GET', f'{ASSET}/characters?limit=100'): {'items': []},
        ('POST', f'{ASSET}/characters'): lambda body: {'id': {'하람': 'c1', '무진': 'c2'}[body['name']]},
        ('GET', f'{ASSET}/worlds?limit=100'): {'items': []},
        ('POST', f'{ASSET}/worlds'): {'id': 'w1'},
        **{
            (method, f'{ASSET}/{path}{tail}'): answer
            for path in ('characters/c1', 'characters/c2', 'worlds/w1')
            for method, tail, answer in (
                ('PATCH', '', {}),
                ('GET', '/publish-check', {'ready': True, 'problems': []}),
                ('POST', '/versions', {'number': 1}),
            )
        },
    }


class WorksTest(unittest.TestCase):
    def test_publishes_the_lorebook_then_characters_then_the_world(self):
        api = FakeApi(empty_asset())

        made = seed_works(api)

        self.assertEqual([one.id for one in made], ['c1', 'c2', 'w1'])
        self.assertEqual([one.state for one in made], ['created'] * 3)
        versions = api.paths('POST')
        order = [versions.index(f'{ASSET}/{path}/versions') for path in ('lorebooks/al1', 'characters/c1', 'worlds/w1')]
        self.assertEqual(order, sorted(order))
        self.assertEqual(api.body('PATCH', f'{ASSET}/worlds/w1'), {'visibility': 'public'})
        cast = {member['id']: member['character_id'] for member in api.body('POST', f'{ASSET}/worlds')['cast']}
        self.assertEqual(cast, {'mujin': 'c2', 'haram': 'c1'})
        self.assertEqual(api.body('POST', f'{ASSET}/characters')['lorebooks'], ['al1'])

    def test_public_published_works_are_kept(self):
        answers = empty_asset()
        answers[('GET', f'{ASSET}/lorebooks?limit=100')] = {
            'items': [{'id': 'al1', 'name': content.ASSET_LOREBOOK_NAME, 'latest_version': 1}]
        }
        answers[('GET', f'{ASSET}/characters?limit=100')] = {
            'items': [
                {'id': 'c1', 'name': '하람', 'latest_version': 1, 'visibility': 'public'},
                {'id': 'c2', 'name': '무진', 'latest_version': 2, 'visibility': 'public'},
            ]
        }
        answers[('GET', f'{ASSET}/worlds?limit=100')] = {
            'items': [{'id': 'w1', 'name': content.WORLD_NAME, 'latest_version': 1, 'visibility': 'public'}]
        }
        api = FakeApi(answers)

        self.assertEqual([one.state for one in seed_works(api)], ['kept'] * 3)
        self.assertEqual(api.paths('POST'), [])
        self.assertEqual(api.paths('PATCH'), [])


class ContentTest(unittest.TestCase):
    def test_the_scenario_points_only_at_entries_that_exist(self):
        body = content.scenario_body('r1', 'm', 'l1', 'b1', IDS, 'm1')
        text = json.dumps(body)
        self.assertIn(IDS[content.QUEST], text)
        self.assertEqual(body['start_place'], IDS[content.START_PLACE])

    def test_achievement_ids_are_unique_within_each_work(self):
        works = [
            content.achievements(IDS),
            content.haram_body('al1')['achievements'],
            content.world_body('al1', 'c2', 'c1')['achievements'],
        ]
        for achievements in works:
            ids = [achievement['id'] for achievement in achievements]
            self.assertEqual(len(ids), len(set(ids)))

    def test_haram_reaches_the_hidden_stage_by_the_tea(self):
        haram = content.haram_body('al1')
        stage = next(item for one in haram['achievements'] for item in one['when']['items'] if item.get('value'))
        reached = {s['name']: s['at'] for s in haram['affection']['stages']}[stage['value']]
        self.assertLessEqual(reached, haram['affection']['rules'][0]['change'])


class ReportTest(unittest.TestCase):
    def test_lists_the_pages_to_open(self):
        made = [
            Made('TRPG 시나리오', '꺼진 등대', 's1', 'created'),
            Made('story 세계관', '소금 시장의 밤', 'w1', 'kept'),
        ]
        text = report(made, 'https://staging.ai-trpg.test')
        self.assertIn('https://staging.ai-trpg.test/trpg/scenarios/s1', text)
        self.assertIn('https://staging.ai-trpg.test/story/worlds/w1', text)
        self.assertIn('이미 게시돼 있었다', text)


if __name__ == '__main__':
    unittest.main()
