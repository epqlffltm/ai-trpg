# .github/scripts/dashboard_scope.py

"""
Grafana 의 대시보드(docker/grafana/dashboards/*.json)가 정해 둔 규칙을 지키는지 보고, 쿼리가 오류 없이 도는지 본다(#25).

규칙(docs/observability.md 의 "대시보드"):
  - 서버마다 파일 하나다. 파일 이름이 서비스 이름이고, 대시보드의 uid 도 그 이름이다
    (billing-server.json, uid billing-server)
  - 데이터 소스는 uid 로 고정해 부른다(prometheus, loki). 저장소를 Mimir 로 바꿀 때 데이터 소스의 주소만 바뀐다.
    화면에서 "Export for sharing externally" 로 내보낸 파일의 ${DS_PROMETHEUS} 같은 자리와 __inputs 는 받지 않는다
  - Prometheus 의 쿼리는 모든 선택자({…})에 그 서버의 service 를 건다.
    다섯 서버가 같은 이름(http_server_requests_total)을 쓰므로, 빠뜨리면 다른 서버의 요청까지 섞여 보인다
  - 패널의 id 는 대시보드 안에서 겹치지 않는다

    사용: python3 .github/scripts/dashboard_scope.py docker/grafana/dashboards
          DASHBOARD_QUERY_AUTH=admin:<비밀번호> python3 .github/scripts/dashboard_scope.py docker/grafana/dashboards \\
            --query http://127.0.0.1:3000/api/datasources/proxy/uid/prometheus

--query 를 주면 규칙을 본 뒤 Prometheus 의 쿼리를 그 주소(Prometheus 의 API 와 같은 모양)로 하나씩 돌려
오류가 없는지 본다.
Grafana 의 데이터 소스 프록시를 주면 Grafana 가 그 데이터 소스로 쿼리를 돌릴 수 있는지까지 본다.
값이 없는 것(아직 일어나지 않은 일)은 오류가 아니다. stack-smoke.sh 의 check 가 부른다. 표준 라이브러리만 쓴다.
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# 대시보드가 부를 수 있는 데이터 소스의 uid(docker/grafana/provisioning/datasources)
DATASOURCE_UIDS = frozenset({'prometheus', 'loki'})

# Grafana 가 쿼리를 보내기 전에 채우는 자리. 직접 돌릴 때는 이 값으로 채운다
MACROS = {
    '$__rate_interval': '1m',
    '$__interval': '1m',
    '$__range': '1h',
}

# 쿼리 안의 label 선택자. 대시보드의 이름표({{route}})는 legendFormat 에만 있고 쿼리에는 없다
SELECTOR = re.compile(r'\{[^{}]*\}')

# 쿼리 하나에 기다리는 시간(초)
QUERY_TIMEOUT = 10


@dataclass(frozen=True)
class Query:
    """대시보드의 Prometheus 쿼리 하나."""

    dashboard: str
    panel: str
    expr: str


def load_dashboards(folder: Path) -> dict[str, dict]:
    """폴더의 대시보드를 파일 이름(서비스 이름)마다 읽는다."""
    return {path.stem: json.loads(path.read_text(encoding='utf-8')) for path in sorted(folder.glob('*.json'))}


def walk_panels(panels: list[dict]) -> list[dict]:
    """패널을 모두 편다. 접힌 줄(row)은 그 안에 패널을 품는다."""
    flat = []
    for panel in panels:
        flat.append(panel)
        flat.extend(walk_panels(panel.get('panels', [])))
    return flat


def datasource_uid(holder: dict) -> str | None:
    """패널이나 쿼리가 부르는 데이터 소스의 uid. 적지 않았으면 None 이다(대시보드의 기본을 따른다)."""
    datasource = holder.get('datasource')
    if datasource is None:
        return None
    if isinstance(datasource, dict):
        return datasource.get('uid')
    # 옛 모양은 데이터 소스의 이름(글자)만 적는다
    return str(datasource)


def check_identity(name: str, dashboard: dict) -> list[str]:
    """파일 이름, uid, 제목을 본다."""
    problems = []
    if dashboard.get('uid') != name:
        problems.append(f'{name}: uid 가 {dashboard.get("uid")!r} 다. 파일 이름({name})과 같아야 한다')
    if not dashboard.get('title'):
        problems.append(f'{name}: 제목이 없다')
    if '__inputs' in dashboard:
        problems.append(f'{name}: __inputs 가 있다. 바깥에 나누려고 내보낸 파일이다. 그냥 Export 한 JSON 을 쓴다')
    return problems


def check_datasources(name: str, panels: list[dict]) -> list[str]:
    """패널과 쿼리가 정해 둔 uid 의 데이터 소스만 부르는지 본다."""
    problems = []
    for panel in panels:
        for holder in [panel, *panel.get('targets', [])]:
            uid = datasource_uid(holder)
            if uid is not None and uid not in DATASOURCE_UIDS:
                problems.append(
                    f'{name}: 패널 {panel.get("title")!r} 이 데이터 소스 {uid!r} 를 부른다. '
                    f'{sorted(DATASOURCE_UIDS)} 가운데 하나여야 한다'
                )
    return problems


def check_panel_ids(name: str, panels: list[dict]) -> list[str]:
    """패널의 id 가 겹치지 않는지 본다. 겹치면 Grafana 가 패널 하나를 잃는다."""
    seen, problems = set(), []
    for panel in panels:
        panel_id = panel.get('id')
        if panel_id in seen:
            problems.append(f'{name}: 패널의 id {panel_id} 가 겹친다')
        seen.add(panel_id)
    return problems


def prometheus_queries(name: str, panels: list[dict]) -> list[Query]:
    """Prometheus 를 부르는 쿼리를 모은다. Loki 의 쿼리(LogQL)는 넣지 않는다."""
    queries = []
    for panel in panels:
        for target in panel.get('targets', []):
            uid = datasource_uid(target) or datasource_uid(panel)
            if uid == 'prometheus' and target.get('expr'):
                queries.append(Query(name, str(panel.get('title')), target['expr']))
    return queries


def check_service_filter(query: Query) -> list[str]:
    """쿼리의 모든 선택자에 그 서버의 service 가 걸렸는지 본다."""
    wanted = f'service="{query.dashboard}"'
    selectors = SELECTOR.findall(query.expr)
    if not selectors:
        return [f'{query.dashboard}: 패널 {query.panel!r} 의 쿼리에 선택자가 없다. {wanted} 를 건다: {query.expr}']
    return [
        f'{query.dashboard}: 패널 {query.panel!r} 의 선택자 {selector} 에 {wanted} 가 없다'
        for selector in selectors
        if wanted not in selector
    ]


def check_dashboard(name: str, dashboard: dict) -> list[str]:
    """대시보드 하나의 규칙을 모두 본다."""
    panels = walk_panels(dashboard.get('panels', []))
    problems = check_identity(name, dashboard) + check_datasources(name, panels) + check_panel_ids(name, panels)
    for query in prometheus_queries(name, panels):
        problems += check_service_filter(query)
    return problems


def check(dashboards: dict[str, dict]) -> list[str]:
    """대시보드들의 규칙을 본다. 어긋난 것들을 돌려준다. 대시보드가 하나도 없는 것도 어긋난 것이다."""
    if not dashboards:
        return ['대시보드가 하나도 없다']
    problems = []
    for name, dashboard in dashboards.items():
        problems += check_dashboard(name, dashboard)
    return problems


def fill_macros(expr: str) -> str:
    """Grafana 가 채우는 자리를 정해 둔 값으로 채운다. 긴 이름부터 채운다($__range 가 $__rate_interval 을 먹지 않게)."""
    for macro in sorted(MACROS, key=len, reverse=True):
        expr = expr.replace(macro, MACROS[macro])
    return expr


def run_query(base: str, expr: str, auth: str | None) -> str | None:
    """쿼리 하나를 지금 시각으로 돌린다. 오류가 없으면 None, 있으면 그 까닭이다."""
    url = f'{base.rstrip("/")}/api/v1/query?{urllib.parse.urlencode({"query": fill_macros(expr)})}'
    request = urllib.request.Request(url)
    if auth:
        request.add_header('Authorization', 'Basic ' + base64.b64encode(auth.encode()).decode())
    try:
        with urllib.request.urlopen(request, timeout=QUERY_TIMEOUT) as response:
            body = json.load(response)
    except urllib.error.HTTPError as error:
        return f'{error.code} {error.read().decode(errors="replace")[:300]}'
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return str(error)
    return None if body.get('status') == 'success' else str(body.get('error', body))


def check_queries(dashboards: dict[str, dict], base: str, auth: str | None) -> list[str]:
    """모든 Prometheus 쿼리를 돌려 오류가 난 것을 돌려준다."""
    problems = []
    for name, dashboard in dashboards.items():
        for query in prometheus_queries(name, walk_panels(dashboard.get('panels', []))):
            failure = run_query(base, query.expr, auth)
            if failure:
                problems.append(f'{name}: 패널 {query.panel!r} 의 쿼리가 실패했다: {failure}')
    return problems


def parse_args(argv: list[str]) -> argparse.Namespace:
    """명령 줄을 읽는다."""
    parser = argparse.ArgumentParser(description='Grafana 대시보드의 규칙과 쿼리를 본다')
    parser.add_argument('folder', type=Path, help='대시보드 JSON 이 든 폴더')
    parser.add_argument('--query', metavar='URL', help='쿼리를 돌릴 Prometheus API 의 주소(Grafana 의 프록시도 된다)')
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """규칙을 보고, --query 가 있으면 쿼리도 돌린다. 어긋난 것을 찍고 끝 코드를 돌려준다."""
    args = parse_args(argv)
    dashboards = load_dashboards(args.folder)
    problems = check(dashboards)
    if not problems and args.query:
        problems = check_queries(dashboards, args.query, os.environ.get('DASHBOARD_QUERY_AUTH'))
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
