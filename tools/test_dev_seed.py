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
    seed_scenario,
    seed_table,
)

PROXY = 'http://127.0.0.1:8080'


class FakeGame:
    """게임 서버의 흉내. (방법, 주소) 마다 답을 정하고 받은 요청을 적는다. 정하지 않은 것은 시험을 실패시킨다."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, proxy: str, token: str, method: str, path: str, body: dict | None = None) -> dict:
        self.calls.append((method, path, body))
        answer = self.answers[(method, path)]
        if isinstance(answer, Exception):
            raise answer
        return answer


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
        body = scenario_body('r1', 'm1')
        self.assertEqual(len(body['openings']), 2)
        self.assertEqual(len(body['pregens']), 3)
        for pregen in body['pregens']:
            self.assertEqual(sorted(pregen['sheet']['abilities']), ['cha', 'con', 'dex', 'int', 'str', 'wis'])

    def test_creates_and_publishes_when_missing(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/scenarios?limit=100'): {'items': [], 'total': 0},
                ('GET', '/api/v1/game/tables/narration-models'): {'models': [{'slug': 'm1'}]},
                ('POST', '/api/v1/game/rulebooks'): {'id': 'r1'},
                ('POST', '/api/v1/game/scenarios'): {'id': 's1'},
                ('PATCH', '/api/v1/game/scenarios/s1/listing'): {},
                ('POST', '/api/v1/game/scenarios/s1/versions'): {'number': 1},
                ('PUT', '/api/v1/game/scenarios/s1/listing/publication'): {},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_scenario(PROXY, 't'), ('s1', True))
        self.assertEqual(game.calls[-1], ('PUT', '/api/v1/game/scenarios/s1/listing/publication', {'version': 1}))
        self.assertEqual(game.calls[4][2]['genres'], ['horror', 'mystery'])

    def test_existing_listed_scenario_is_left_alone(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/scenarios?limit=100'): {'items': [{'id': 's1', 'title': SEED_TITLE}]},
                ('GET', '/api/v1/game/listings/s1'): {'scenario_id': 's1'},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_scenario(PROXY, 't'), ('s1', False))
        self.assertEqual(len(game.calls), 2)

    def test_existing_unlisted_scenario_is_published(self):
        game = FakeGame(
            {
                ('GET', '/api/v1/game/scenarios?limit=100'): {'items': [{'id': 's1', 'title': SEED_TITLE}]},
                ('GET', '/api/v1/game/listings/s1'): SeedError('404'),
                ('POST', '/api/v1/game/scenarios/s1/versions'): {'number': 2},
                ('PUT', '/api/v1/game/scenarios/s1/listing/publication'): {},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            seed_scenario(PROXY, 't')
        self.assertEqual(game.calls[-1][2], {'version': 2})


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
                ('GET', '/api/v1/game/tables/t1'): {'id': 't1', 'invite_code': 'ABC'},
            }
        )
        with mock.patch.object(dev_seed, 'call', game):
            self.assertEqual(seed_table(PROXY, 't', 's1'), {'id': 't1', 'invite_code': 'ABC'})

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


class ReportTest(unittest.TestCase):
    def test_lists_accounts_addresses_and_where_the_codes_are(self):
        seeded = dev_seed.Seeded(
            accounts=[Account('seed_host', 'p1', 't1'), Account('seed_guest', 'p2', 't2')],
            scenario_id='s1',
            created_scenario=True,
            table={'id': 't9', 'invite_code': 'ABC'},
        )
        text = report(seeded, PROXY, 'pw')
        self.assertIn('방장: seed_host / pw', text)
        self.assertIn('손님: seed_guest / pw', text)
        self.assertIn(f'{PROXY}/trpg/tables/t9', text)
        self.assertIn('docker compose --profile app logs -f auth-mail', text)
        self.assertNotIn('t1', text.replace('/t9', ''))


if __name__ == '__main__':
    unittest.main()
