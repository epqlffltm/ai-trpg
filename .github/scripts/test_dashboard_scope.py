# .github/scripts/test_dashboard_scope.py

"""
대시보드의 규칙 검사(dashboard_scope.py)를 본다. Grafana 없이, 작은 대시보드를 만들어 넣는다.

    사용: python3 -m unittest discover -s .github/scripts -p 'test_dashboard_scope.py'

stack-smoke.sh 의 check 가 실제 대시보드를 검사하기 전에 부른다(test_*_scope.py).
규칙이 틀리면 섞인 패널을 놓치고 초록이 된다.
"""

import json
import tempfile
import unittest
from pathlib import Path

from dashboard_scope import check, fill_macros, load_dashboards

PROMETHEUS = {'type': 'prometheus', 'uid': 'prometheus'}


def panel(expr: str, panel_id: int = 1, datasource: dict | None = None) -> dict:
    """Prometheus 쿼리 하나를 가진 패널."""
    source = datasource or PROMETHEUS
    return {
        'id': panel_id,
        'title': f'패널 {panel_id}',
        'datasource': source,
        'targets': [{'datasource': source, 'expr': expr, 'refId': 'A'}],
    }


def dashboard(*panels: dict, uid: str = 'billing-server') -> dict:
    """결제 서버의 대시보드."""
    return {'uid': uid, 'title': '결제 서버', 'panels': list(panels)}


GOOD = 'sum(rate(http_server_requests_total{service="billing-server"}[$__rate_interval]))'


class DashboardScopeTests(unittest.TestCase):
    def test_passes_when_every_selector_names_the_server(self):
        ratio = (
            'sum(rate(http_server_requests_total{service="billing-server", status_code=~"5.."}[5m]))'
            ' / sum(rate(http_server_requests_total{service="billing-server"}[5m]))'
        )

        self.assertEqual(check({'billing-server': dashboard(panel(GOOD), panel(ratio, 2))}), [])

    def test_a_selector_without_the_service_mixes_servers(self):
        # 서버들이 같은 이름을 쓴다. 나눗셈의 한쪽만 빠뜨려도 다른 서버의 요청이 섞인다
        mixed = (
            'sum(rate(http_server_requests_total{service="billing-server", status_code=~"5.."}[5m]))'
            ' / sum(rate(http_server_requests_total{route="/health"}[5m]))'
        )

        problems = check({'billing-server': dashboard(panel(mixed))})

        self.assertEqual(len(problems), 1)
        self.assertIn('{route="/health"}', problems[0])

    def test_infrastructure_dashboards_name_their_job(self):
        # Alloy 가 긁는 인프라에는 service 가 없다. 그 job 으로 가른다
        board = dashboard(panel('pg_up{job="postgres"}'), uid='postgres')

        self.assertEqual(check({'postgres': board}), [])

    def test_another_job_does_not_count(self):
        board = dashboard(panel('redis_up{job="redis"}'), uid='postgres')

        self.assertEqual(len(check({'postgres': board})), 1)

    def test_a_query_without_any_selector_is_refused(self):
        problems = check({'billing-server': dashboard(panel('sum(rate(http_server_requests_total[5m]))'))})

        self.assertEqual(len(problems), 1)
        self.assertIn('선택자가 없다', problems[0])

    def test_another_servers_name_does_not_count(self):
        problems = check({'billing-server': dashboard(panel('db_up{service="trpg-server"}'))})

        self.assertEqual(len(problems), 1)

    def test_the_uid_must_be_the_file_name(self):
        problems = check({'billing-server': dashboard(panel(GOOD), uid='billing')})

        self.assertEqual(len(problems), 1)
        self.assertIn('uid', problems[0])

    def test_a_datasource_variable_from_an_external_export_is_refused(self):
        # "Export for sharing externally" 로 내보내면 데이터 소스가 ${DS_PROMETHEUS} 자리로 바뀐다
        exported = dashboard(panel(GOOD, datasource={'type': 'prometheus', 'uid': '${DS_PROMETHEUS}'}))
        exported['__inputs'] = [{'name': 'DS_PROMETHEUS'}]

        problems = check({'billing-server': exported})

        self.assertTrue(any('__inputs' in problem for problem in problems))
        self.assertTrue(any('${DS_PROMETHEUS}' in problem for problem in problems))

    def test_panels_inside_a_collapsed_row_are_checked(self):
        row = {'id': 1, 'type': 'row', 'title': '접힌 줄', 'panels': [panel('db_up', 2)]}

        problems = check({'billing-server': dashboard(row)})

        self.assertEqual(len(problems), 1)

    def test_loki_queries_are_not_held_to_the_prometheus_rule(self):
        logs = panel('{container="billing-server"} |= "error"', datasource={'type': 'loki', 'uid': 'loki'})

        self.assertEqual(check({'billing-server': dashboard(panel(GOOD), {**logs, 'id': 2})}), [])

    def test_panel_ids_must_not_repeat(self):
        problems = check({'billing-server': dashboard(panel(GOOD, 1), panel(GOOD, 1))})

        self.assertEqual(len(problems), 1)
        self.assertIn('id 1', problems[0])

    def test_no_dashboards_at_all_is_a_problem(self):
        self.assertEqual(check({}), ['대시보드가 하나도 없다'])

    def test_macros_are_filled_before_querying(self):
        filled = fill_macros('rate(x{service="a"}[$__rate_interval]) + increase(x{service="a"}[$__range])')

        self.assertEqual(filled, 'rate(x{service="a"}[1m]) + increase(x{service="a"}[1h])')

    def test_dashboards_are_named_by_their_file(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'billing-server.json').write_text(json.dumps(dashboard(panel(GOOD))), encoding='utf-8')

            self.assertEqual(list(load_dashboards(Path(folder))), ['billing-server'])

    def test_the_dashboards_in_the_repository_hold(self):
        folder = Path(__file__).resolve().parents[2] / 'docker' / 'grafana' / 'dashboards'

        self.assertEqual(check(load_dashboards(folder)), [])


if __name__ == '__main__':
    unittest.main()
