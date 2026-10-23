# tools/test_dev_seed.py

"""
견본을 채우는 스크립트(dev_seed.py)를 본다. compose 와 서버를 부르지 않는다.
부르는 곳(subprocess, urllib)을 가짜로 바꾼다.

    사용: python3 -m unittest discover -s tools -p 'test_*.py'

인증 서버의 컨테이너에서 도는 dev_seed_accounts.py 는 Django 가 있어야 해서 여기서 부르지 않는다.
"""

import json
import subprocess
import unittest
from unittest import mock

import dev_seed
import dev_seed_world
from dev_seed import (
    RESULT_PREFIX,
    SEED_TITLE,
    Account,
    SeedError,
    ensure_local,
    parse_seed_result,
    pick_model,
    proxy_port,
    report,
    scenario_body,
    seed_lorebook,
    seed_scenario,
    seed_table,
    verify_identity,
)
from dev_seed_world import ENTRIES, LOREBOOK_TITLE, world_fields

PROXY = 'http://127.0.0.1:8080'
LOREBOOKS = '/api/v1/game/lorebooks'

# 지금 세계를 담은 시나리오의 답(맵, 화폐, 장비가 있다)
CURRENT_SCENARIO = {'id': 's1', 'start_place': 'e0', 'currency': {'name': '은화'}, 'items': [{'slots': ['body']}]}

# 로어북의 항목이 모두 있을 때의 이름에서 ID 로 가는 표
IDS = {entry['name']: f'e{index}' for index, entry in enumerate(ENTRIES)}


def lorebook_answers(entries: list[dict]) -> dict:
    """로어북이 이미 있고 항목이 entries 만큼 있는 게임 서버의 답. 없는 항목은 만들면 'new-<이름>' 이 된다"""
    answers = {
        ('GET', f'{LOREBOOKS}?limit=100'): {'items': [{'id': 'l1', 'title': LOREBOOK_TITLE}]},
        ('GET', f'{LOREBOOKS}/l1/entries'): entries,
    }
    return answers


class FakeGame:
    """
    게임 서버의 흉내. (방법, 주소) 마다 답을 정하고 받은 요청을 적는다. 정하지 않은 것은 시험을 실패시킨다.
    답이 부를 수 있는 것이면 부를 때마다 불러 새 답을 받는다(만들 때마다 다른 ID)
    """

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, proxy: str, token: str, method: str, path: str, body: dict | None = None) -> dict:
        self.calls.append((method, path, body))
        answer = self.answers[(method, path)]
        if isinstance(answer, Exception):
            raise answer
        return answer() if callable(answer) else answer


class ProxyTest(unittest.TestCase):
    def test_port_comes_from_root_env(self):
        self.assertEqual(proxy_port('# PROXY_PORT=9000\nPROXY_PORT=8081\n'), '8081')
        self.assertEqual(proxy_port('# PROXY_PORT=9000\n'), '8080')
        self.assertEqual(proxy_port(''), '8080')

    def test_only_this_pc(self):
        ensure_local('http://127.0.0.1:8080')
        ensure_local('http://localhost:8080')
        with self.assertRaises(SeedError):
            ensure_local('https://staging.example.com')


class AccountsTest(unittest.TestCase):
    def test_reads_the_last_result_line_and_skips_other_output(self):
        accounts = [{'username': 'seed_host', 'public_id': 'p1', 'access_token': 't1'}]
        output = f'경고 한 줄\n{RESULT_PREFIX}[]\n{RESULT_PREFIX}{json.dumps(accounts)}\n'
        self.assertEqual(parse_seed_result(output), [Account('seed_host', 'p1', 't1')])

    def test_no_result_is_an_error(self):
        with self.assertRaises(SeedError):
            parse_seed_result('Traceback ...')

    def test_runs_the_script_in_the_auth_container_with_the_accounts_in_env(self):
        accounts = [{'username': 'seed_host', 'public_id': 'p1', 'access_token': 't1'}]
        done = subprocess.CompletedProcess([], 0, stdout=f'{RESULT_PREFIX}{json.dumps(accounts)}'.encode(), stderr=b'')
        with mock.patch.object(dev_seed.subprocess, 'run', return_value=done) as run:
            self.assertEqual(dev_seed.seed_accounts('pw'), [Account('seed_host', 'p1', 't1')])
        command = run.call_args.args[0]
        self.assertEqual(command[:6], ['docker', 'compose', '--profile', 'app', 'exec', '-T'])
        self.assertIn('auth-server', command)
        self.assertEqual(command[-2], '-c')
        self.assertIn('issue_token_pair', command[-1])
        sent = json.loads(command[command.index('-e') + 1].removeprefix('SEED_ACCOUNTS='))
        self.assertEqual([spec['username'] for spec in sent], ['seed_host', 'seed_guest'])
        self.assertTrue(all(spec['password'] == 'pw' for spec in sent))

    def test_failure_of_the_container_is_an_error(self):
        done = subprocess.CompletedProcess([], 1, stdout=b'', stderr=b'no such service')
        with (
            mock.patch.object(dev_seed.subprocess, 'run', return_value=done),
            self.assertRaisesRegex(SeedError, 'no such'),
        ):
            dev_seed.seed_accounts('pw')


class ScenarioTest(unittest.TestCase):
    def test_model_must_be_offered(self):
        self.assertEqual(pick_model({'models': [{'slug': 'glm-4-7-flash'}, {'slug': 'x'}]}), 'glm-4-7-flash')
        with self.assertRaisesRegex(SeedError, 'scripts.models sync'):
            pick_model({'free': True, 'models': []})

    def test_body_has_two_openings_and_three_pregens_with_full_sheets(self):
        body = scenario_body('r1', 'm1', world_fields(IDS, 'l1'))
        self.assertEqual(len(body['openings']), 2)
        self.assertEqual(len(body['pregens']), 3)
        for pregen in body['pregens']:
            self.assertEqual(sorted(pregen['sheet']['abilities']), ['cha', 'con', 'dex', 'int', 'str', 'wis'])
        self.assertEqual(body['character_modes'], ['pregen', 'custom', 'manual', 'point_buy', 'rolled'])

    def test_creates_and_publishes_when_missing(self):
        answers = {
            ('GET', '/api/v1/game/scenarios?limit=100'): {'items': [], 'total': 0},
            ('GET', '/api/v1/game/tables/narration-models'): {'models': [{'slug': 'm1'}]},
            ('GET', f'{LOREBOOKS}?limit=100'): {'items': []},
            ('POST', LOREBOOKS): {'id': 'l1'},
            ('POST', '/api/v1/game/rulebooks'): {'id': 'r1'},
            ('POST', '/api/v1/game/scenarios'): {'id': 's1'},
            ('PATCH', '/api/v1/game/scenarios/s1/listing'): {},
            ('POST', '/api/v1/game/scenarios/s1/versions'): {'number': 1},
            ('PUT', '/api/v1/game/scenarios/s1/listing/publication'): {},
        }
        game = FakeGame(answers)
        made = iter(range(len(ENTRIES)))
        answers[('POST', f'{LOREBOOKS}/l1/entries')] = mock.Mock(side_effect=lambda: {'id': f'e{next(made)}'})
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_scenario(PROXY, 't'), ('s1', 'created'))
        self.assertEqual(game.calls[-1], ('PUT', '/api/v1/game/scenarios/s1/listing/publication', {'version': 1}))
        created = next(
            body for method, path, body in game.calls if (method, path) == ('POST', '/api/v1/game/scenarios')
        )
        self.assertEqual(created['start_place'], IDS['수도원 문'])
        self.assertEqual(created['lorebook_ids'], ['l1'])
        listing = next(body for method, path, body in game.calls if path.endswith('/listing') and method == 'PATCH')
        self.assertEqual(listing['genres'], ['horror', 'mystery'])

    def test_existing_listed_scenario_with_world_is_left_alone(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/scenarios?limit=100'): {'items': [{'id': 's1', 'title': SEED_TITLE}]},
                ('GET', '/api/v1/game/scenarios/s1'): CURRENT_SCENARIO,
                ('GET', '/api/v1/game/listings/s1'): {'scenario_id': 's1'},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_scenario(PROXY, 't'), ('s1', 'kept'))
        self.assertEqual(len(game.calls), 3)

    def test_existing_unlisted_scenario_is_published(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/scenarios?limit=100'): {'items': [{'id': 's1', 'title': SEED_TITLE}]},
                ('GET', '/api/v1/game/scenarios/s1'): CURRENT_SCENARIO,
                ('GET', '/api/v1/game/listings/s1'): SeedError('404'),
                ('POST', '/api/v1/game/scenarios/s1/versions'): {'number': 2},
                ('PUT', '/api/v1/game/scenarios/s1/listing/publication'): {},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            seed_scenario(PROXY, 't')
        self.assertEqual(game.calls[-1][2], {'version': 2})

    def test_old_seed_without_a_map_gets_the_world_and_a_new_version(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/scenarios?limit=100'): {'items': [{'id': 's1', 'title': SEED_TITLE}]},
                ('GET', '/api/v1/game/scenarios/s1'): {'id': 's1', 'start_place': None},
                ('GET', '/api/v1/game/tables/narration-models'): {'models': [{'slug': 'm1'}]},
                **lorebook_answers([{'id': IDS[name], 'name': name} for name in IDS]),
                ('PATCH', '/api/v1/game/scenarios/s1'): {},
                ('POST', '/api/v1/game/scenarios/s1/versions'): {'number': 3},
                ('PUT', '/api/v1/game/scenarios/s1/listing/publication'): {},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_scenario(PROXY, 't'), ('s1', 'upgraded'))
        patched = next(body for method, path, body in game.calls if method == 'PATCH')
        self.assertNotIn('title', patched)
        self.assertNotIn('rulebook_id', patched)
        self.assertEqual(patched['start_place'], IDS['수도원 문'])
        self.assertEqual(game.calls[-1][2], {'version': 3})

    def test_seed_with_a_map_but_no_currency_is_upgraded_too(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/scenarios?limit=100'): {'items': [{'id': 's1', 'title': SEED_TITLE}]},
                ('GET', '/api/v1/game/scenarios/s1'): {'id': 's1', 'start_place': 'e0', 'currency': None},
                ('GET', '/api/v1/game/tables/narration-models'): {'models': [{'slug': 'm1'}]},
                **lorebook_answers([{'id': IDS[name], 'name': name} for name in IDS if name != '떠돌이 행상']),
                ('POST', f'{LOREBOOKS}/l1/entries'): {'id': 'new'},
                ('PATCH', '/api/v1/game/scenarios/s1'): {},
                ('POST', '/api/v1/game/scenarios/s1/versions'): {'number': 4},
                ('PUT', '/api/v1/game/scenarios/s1/listing/publication'): {},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_scenario(PROXY, 't'), ('s1', 'upgraded'))
        patched = next(body for method, path, body in game.calls if method == 'PATCH')
        self.assertEqual(patched['currency'], dev_seed_world.CURRENCY)
        merchant = next(npc for npc in patched['npc_sheets'] if npc.get('merchant'))
        self.assertEqual(merchant['entry_id'], 'new')


class LorebookTest(unittest.TestCase):
    def test_makes_only_missing_entries(self):
        have = [{'id': IDS[name], 'name': name} for name in IDS if name != '은 성배']
        answers = lorebook_answers(have)
        answers[('POST', f'{LOREBOOKS}/l1/entries')] = {'id': 'new'}
        game = FakeGame(answers)
        with mock.patch.object(dev_seed, 'call', game):
            lorebook_id, ids = seed_lorebook(PROXY, 't')
        self.assertEqual(lorebook_id, 'l1')
        self.assertEqual(ids['은 성배'], 'new')
        posts = [body for method, path, body in game.calls if method == 'POST']
        self.assertEqual([body['name'] for body in posts], ['은 성배'])


class WorldTest(unittest.TestCase):
    def test_every_name_the_world_points_to_is_an_entry(self):
        fields = world_fields(IDS, 'l1')
        text = str(fields)
        self.assertNotIn('KeyError', text)
        self.assertEqual({entry['kind'] for entry in ENTRIES}, {'place', 'item', 'person', 'event'})
        hidden = [route for route in fields['routes'] if route.get('visibility') == 'hidden']
        self.assertTrue(all('find' in route for route in hidden))
        self.assertEqual(dev_seed_world.START_PLACE, '수도원 문')

    def test_money_needs_the_currency_and_the_merchant_sells_priced_items(self):
        fields = world_fields(IDS, 'l1')
        self.assertEqual(fields['currency']['name'], '은화')
        priced = {rule['entry_id'] for rule in fields['items'] if rule.get('price')}
        merchant = next(npc for npc in fields['npc_sheets'] if npc.get('merchant'))
        self.assertTrue({line['entry_id'] for line in merchant['inventory']} <= priced)
        self.assertNotIn(IDS['녹슨 열쇠'], priced)

    def test_is_current_needs_a_world_a_currency_and_gear(self):
        gear = [{'slots': ['body']}]
        self.assertTrue(dev_seed_world.is_current({'start_place': 'p', 'currency': {'name': '은화'}, 'items': gear}))
        self.assertTrue(dev_seed_world.is_current({'map': {'places': []}, 'currency': {'name': '은화'}, 'items': gear}))
        self.assertFalse(dev_seed_world.is_current({'start_place': 'p', 'currency': None, 'items': gear}))
        self.assertFalse(dev_seed_world.is_current({'currency': {'name': '은화'}, 'items': gear}))
        self.assertFalse(
            dev_seed_world.is_current({'start_place': 'p', 'currency': {'name': '은화'}, 'items': [{'slots': []}]})
        )

    def test_a_pregen_starts_wearing_gear_that_fits(self):
        fields = world_fields(IDS, 'l1')
        rules = {rule['entry_id']: rule for rule in fields['items']}
        worn = [line for pregen in fields['pregens'] for line in pregen.get('items', []) if line.get('wear')]
        self.assertTrue(worn)
        for line in worn:
            rule = rules[line['entry_id']]
            self.assertTrue(set(line['wear']) <= set(rule['slots']))
            self.assertEqual(len(line['wear']), rule.get('slot_count', 1))


class TableTest(unittest.TestCase):
    def test_reuses_a_recruiting_table_of_the_scenario(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/tables?limit=100'): {
                    'items': [
                        {'id': 'old', 'scenario_id': 's1', 'status': 'ended'},
                        {'id': 't1', 'scenario_id': 's1', 'status': 'recruiting'},
                    ]
                },
                ('GET', '/api/v1/game/tables/t1'): {
                    'id': 't1',
                    'invite_code': 'ABC',
                    'map': {'places': []},
                    'currency': {'name': '은화'},
                    'items': [{'slots': ['body']}],
                },
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_table(PROXY, 't', 's1')['id'], 't1')

    def test_a_table_of_the_version_without_currency_is_not_reused(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/tables?limit=100'): {
                    'items': [{'id': 't1', 'scenario_id': 's1', 'status': 'recruiting'}]
                },
                ('GET', '/api/v1/game/tables/t1'): {'id': 't1', 'map': {'places': []}, 'currency': None},
                ('POST', '/api/v1/game/tables'): {'id': 't2', 'invite_code': 'XYZ'},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_table(PROXY, 't', 's1')['id'], 't2')

    def test_a_table_of_the_old_version_without_a_map_is_not_reused(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/tables?limit=100'): {
                    'items': [{'id': 't1', 'scenario_id': 's1', 'status': 'recruiting'}]
                },
                ('GET', '/api/v1/game/tables/t1'): {'id': 't1', 'map': None},
                ('POST', '/api/v1/game/tables'): {'id': 't2', 'invite_code': 'XYZ'},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_table(PROXY, 't', 's1')['id'], 't2')

    def test_opens_a_public_table_when_none(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/tables?limit=100'): {'items': []},
                ('POST', '/api/v1/game/tables'): {'id': 't2', 'invite_code': 'XYZ'},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            seed_table(PROXY, 't', 's1')
        self.assertEqual(game.calls[-1][2], {'scenario_id': 's1', 'capacity': 4, 'is_public': True})


class IdentityTest(unittest.TestCase):
    ACCOUNT = Account('seed_host', 'p1', 't1')
    PATH = '/api/v1/auth/identity/verify'

    def test_verifies_with_a_fake_adult_token_per_account(self):
        game = FakeGame({('POST', self.PATH): {'identity': {'verified': True}}})
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(verify_identity(PROXY, self.ACCOUNT), 'verified')
        self.assertEqual(game.calls, [('POST', self.PATH, {'token': 'fake:seed_host:1990-01-01'})])

    def test_already_verified_is_fine(self):
        already = SeedError('409', status=409, code='identity_already_verified')
        with mock.patch.object(dev_seed, 'call', FakeGame({('POST', self.PATH): already})):
            self.assertEqual(verify_identity(PROXY, self.ACCOUNT), 'already')

    def test_other_failures_stop_the_seed(self):
        unavailable = SeedError('503', status=503, code='identity_unavailable')
        game = FakeGame({('POST', self.PATH): unavailable})
        with mock.patch.object(dev_seed, 'call', game), self.assertRaises(SeedError):
            verify_identity(PROXY, self.ACCOUNT)

    def test_reads_the_error_code_from_the_body(self):
        self.assertEqual(dev_seed.error_code('{"detail": "x", "code": "identity_in_use"}'), 'identity_in_use')
        self.assertIsNone(dev_seed.error_code('<html>'))
        self.assertIsNone(dev_seed.error_code('{"detail": "x"}'))


class ReportTest(unittest.TestCase):
    def test_lists_accounts_addresses_and_where_the_codes_are(self):
        seeded = dev_seed.Seeded(
            accounts=[Account('seed_host', 'p1', 't1'), Account('seed_guest', 'p2', 't2')],
            scenario_id='s1',
            scenario_state='upgraded',
            table={'id': 't9', 'invite_code': 'ABC'},
        )
        text = report(seeded, PROXY, 'pw')
        self.assertIn('방장: seed_host / pw', text)
        self.assertIn('손님: seed_guest / pw', text)
        self.assertIn(f'{PROXY}/trpg/tables/t9', text)
        self.assertIn('docker compose --profile app logs -f auth-mail', text)
        self.assertIn('새 판을 게시했다', text)
        self.assertIn('본인인증', text)
        self.assertNotIn('t1', text.replace('/t9', ''))


if __name__ == '__main__':
    unittest.main()
