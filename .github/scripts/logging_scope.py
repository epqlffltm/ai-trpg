# .github/scripts/logging_scope.py

"""
compose 의 모든 서비스가 로그에 상한을 두었는지 본다(#358).

Docker 의 기본(json-file)은 컨테이너의 로그 파일을 끝없이 키운다. VM 에서 오래 띄우면 디스크가 차고,
그러면 DB 가 쓰지 못해 멈춘다. 서비스마다 크기(max-size)와 파일 수(max-file)의 상한이 있어야 한다.

  - 드라이버는 json-file 이다. docker logs 가 그대로 되고, 나중에 로그를 모을 때(#25) 수집기가 읽는 형식이다.
    드라이버를 적지 않으면 VM 의 기본값을 따르므로 무엇이 될지 모른다
  - max-size 와 max-file 이 모두 있어야 한다. max-file 은 max-size 가 있을 때만 뜻이 있다

docker-compose.yml 의 x-logging 을 서비스마다 logging: *logging 으로 붙이면 통과한다.

    사용: docker compose --profile app config --no-interpolate --no-env-resolution --format json \
            | python3 .github/scripts/logging_scope.py

stack-smoke.sh 의 check 가 부른다. .env 가 없어도 돈다.
"""

import json
import sys

# 쓰는 로그 드라이버
DRIVER = 'json-file'
# 상한을 정하는 설정. 둘 다 있어야 한다
LIMITS = ('max-size', 'max-file')


def logging_problems(name: str, service: dict) -> list[str]:
    """한 서비스의 로그 설정의 문제들."""
    logging = service.get('logging') or {}
    driver = logging.get('driver')
    if not driver:
        return [f'{name}: 로그 설정이 없다. logging: *logging 을 붙인다']
    if driver != DRIVER:
        return [f'{name}: 로그 드라이버가 {driver} 이다. {DRIVER} 여야 한다. logging: *logging 을 붙인다']
    options = logging.get('options') or {}
    return [
        f'{name}: 로그에 {limit} 가 없다. logging: *logging 을 붙인다'
        for limit in LIMITS
        if not str(options.get(limit) or '').strip()
    ]


def check(config: dict) -> list[str]:
    """모든 서비스의 문제들. 비어 있으면 통과다."""
    problems = []
    for name, service in sorted((config.get('services') or {}).items()):
        problems.extend(logging_problems(name, service))
    return problems


def main() -> int:
    problems = check(json.load(sys.stdin))
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print('모든 서비스의 로그에 크기와 파일 수의 상한이 있다')
    return 0


if __name__ == '__main__':
    sys.exit(main())
