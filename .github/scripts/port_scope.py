# .github/scripts/port_scope.py

"""
compose 가 바깥에 여는 포트가 정해 둔 것뿐이고, 모두 이 PC(127.0.0.1)에만 열리는지 본다(#353).

Docker 는 VM 의 방화벽(ufw 등)을 거치지 않고 포트를 연다.
ports 에서 127.0.0.1: 을 빼면 방화벽이 있어도 그 포트가 바로 바깥에 열린다.
서버 넷이 포트를 열면 프록시(요청 수 제한, 경로 차단)를 건너뛰는 길이 생긴다. 이 검사가 그 실수를 PR 에서 잡는다.

  - 포트를 열어도 되는 서비스는 아래의 표(PUBLISHERS)에 있는 것뿐이다
  - 연 포트는 모두 루프백(127.0.0.1, ::1)에 묶여야 한다. 주소를 적지 않으면 모든 주소에 열린다
  - network_mode: host 는 쓰지 않는다. 컨테이너가 VM 의 네트워크를 그대로 쓰면 ports 와 상관없이 다 열린다

바깥에 여는 포트는 staging 의 프록시의 둘(8080 ← VM 의 80, 8443 ← VM 의 443)뿐이다(#451, PUBLIC_PORTS).
그 둘도 --public 을 줄 때(staging 의 설정을 볼 때)만 허용한다. 로컬의 설정은 모두 루프백이어야 한다.
그 밖의 것은 staging 에서도 그대로 루프백이다.

    사용: docker compose --profile app config --no-interpolate --no-env-resolution --format json \
            | python3 .github/scripts/port_scope.py
          docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile app config ... \
            | python3 .github/scripts/port_scope.py --public

stack-smoke.sh 의 check 가 부른다. .env 가 없어도 돈다(${PORT:-8080} 같은 자리를 채우지 않고 읽는다).
"""

import json
import sys
from dataclasses import dataclass

# 포트를 열어도 되는 서비스와 그 까닭
PUBLISHERS = {
    # 바깥의 요청이 들어오는 유일한 입구
    'proxy': '서버 넷 앞의 프록시',
    # 관리자 화면. SSH 터널로만 붙는다(README)
    'auth-server': '관리자 화면',
    # PC 에서 직접 띄운 서버가 붙는다
    'db': 'PC 에서 띄운 서버가 붙는 DB',
    'redis': 'PC 에서 띄운 서버가 붙는 Redis',
    'object-store': 'PC 에서 띄운 서버가 붙는 그림 저장소(S3 의 로컬 흉내)',
    # 로그를 보는 화면(observability 프로필). SSH 터널로만 붙는다(README)
    'grafana': '로그를 보는 화면',
}
# 루프백이 아닌 곳에 열어도 되는 (서비스, 컨테이너 안의 포트). staging 의 설정(--public)에서만 허용한다.
# 프록시가 HTTP(8080)와 HTTPS(8443)를 듣는다. 그 밖의 서비스와 포트는 staging 에서도 루프백이다
PUBLIC_PORTS: frozenset[tuple[str, str]] = frozenset({('proxy', '8080'), ('proxy', '8443')})
# 이 PC 에서만 닿는 주소
LOOPBACK = frozenset({'127.0.0.1', '::1', '[::1]'})


@dataclass(frozen=True)
class Binding:
    """포트 하나가 어디에 열리는가. host_ip 가 빈 글자면 모든 주소다."""

    host_ip: str
    target: str


def split_outside_placeholders(text: str) -> list[str]:
    """쌍점으로 나누되, 채우지 않은 자리(${...}) 안의 쌍점에서는 나누지 않는다."""
    parts, current, depth = [], [], 0
    for index, char in enumerate(text):
        if text.startswith('${', index):
            depth += 1
        elif char == '}' and depth:
            depth -= 1
        if char == ':' and not depth:
            parts.append(''.join(current))
            current = []
        else:
            current.append(char)
    parts.append(''.join(current))
    return parts


def container_port(part: str) -> str:
    """ "8080/tcp" 에서 포트만 꺼낸다."""
    return part.split('/')[0]


def parse_short(text: str) -> Binding:
    """
    짧게 적은 포트("127.0.0.1:8080:8080", "8080:80", "80/tcp", "[::1]:8080:80")를 읽는다.

    셋으로 나뉘면 맨 앞이 주소다. 둘 이하면 주소를 적지 않은 것이라 모든 주소에 열린다.
    주소 자리가 채우지 않은 값이면 무엇이 될지 모르므로 그 글자 그대로 둔다(루프백이 아니다).
    """
    if text.startswith('['):
        host, _, rest = text.partition(']:')
        return Binding(host_ip=f'{host}]', target=container_port(rest.split(':')[-1]))
    parts = split_outside_placeholders(text)
    host_ip = parts[0] if len(parts) == 3 else ''
    return Binding(host_ip=host_ip, target=container_port(parts[-1]))


def bindings_of(service: dict) -> list[Binding]:
    """서비스가 여는 포트들. 짧게 적은 것과 길게 적은 것(host_ip, target)을 모두 읽는다."""
    found = []
    for port in service.get('ports') or []:
        if isinstance(port, dict):
            found.append(Binding(host_ip=str(port.get('host_ip') or ''), target=str(port.get('target', ''))))
        else:
            found.append(parse_short(str(port)))
    return found


def port_problems(name: str, service: dict, public: frozenset[tuple[str, str]]) -> list[str]:
    """한 서비스가 여는 포트의 문제들. public 은 모든 주소에 열어도 되는 (서비스, 포트)다."""
    if service.get('network_mode') == 'host':
        return [f'{name}: network_mode: host 를 쓴다. VM 의 네트워크를 그대로 쓰면 ports 와 상관없이 열린다']
    bindings = bindings_of(service)
    if bindings and name not in PUBLISHERS:
        return [f'{name}: 포트를 연다. 프록시를 건너뛰는 길이 된다. 열어야 하면 PUBLISHERS 에 까닭과 함께 적는다']
    return [
        f'{name}: {binding.target} 을 {binding.host_ip or "모든 주소"} 에 연다. 127.0.0.1 에 묶는다'
        for binding in bindings
        if binding.host_ip not in LOOPBACK and (name, binding.target) not in public
    ]


def check(config: dict, public: frozenset[tuple[str, str]] = frozenset()) -> list[str]:
    """모든 서비스의 문제들. 비어 있으면 통과다. 기본(로컬)은 모든 포트가 루프백이어야 한다."""
    problems = []
    for name, service in sorted((config.get('services') or {}).items()):
        problems.extend(port_problems(name, service, public))
    return problems


def allowed_public_ports(argv: list[str]) -> frozenset[tuple[str, str]]:
    """명령의 인자로 모든 주소에 열어도 되는 포트를 고른다. --public 이면 staging 의 프록시 둘, 없으면 하나도 없다."""
    unknown = [arg for arg in argv if arg != '--public']
    if unknown:
        raise ValueError(f'모르는 인자: {" ".join(unknown)}. 쓸 수 있는 것은 --public 뿐이다')
    return PUBLIC_PORTS if '--public' in argv else frozenset()


def main(argv: list[str]) -> int:
    public = allowed_public_ports(argv)
    problems = check(json.load(sys.stdin), public)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    if public:
        print('바깥에 여는 포트는 프록시의 HTTP 와 HTTPS 뿐이고 그 밖은 모두 이 PC 에만 열린다')
    else:
        print('바깥에 여는 포트는 정해 둔 것뿐이고 모두 이 PC 에만 열린다')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
