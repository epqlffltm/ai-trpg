# docker/certbot/cert_check.py

"""
nginx 가 쓰는 인증서(/tls/fullchain.pem)의 남은 날짜를 본다(#451). certbot 컨테이너의 healthcheck 가 부른다.

인증서는 90일짜리이고 certbot 이 30일 남았을 때부터 갱신한다. 갱신이 조용히 실패하면 석 달 뒤 사이트가 멈춘다.
남은 날짜가 14일보다 적으면(갱신이 2주 넘게 실패했으면) 실패로 끝낸다. 그러면 컨테이너가 unhealthy 가 된다.
인증서가 없거나 읽지 못해도 실패다.

    사용: python3 cert_check.py [인증서 파일]

certbot 이미지에 든 cryptography 를 쓴다. 테스트는 test_cert_check.py 다.
"""

import datetime
import sys
from pathlib import Path

from cryptography import x509

# 기본으로 보는 인증서. compose 의 볼륨(tls)이다
CERT_PATH = Path('/tls/fullchain.pem')
# 이보다 적게 남으면 실패다
MIN_DAYS_LEFT = 14


def expires_at(pem: bytes) -> datetime.datetime:
    """PEM 의 첫 인증서(nginx 가 내주는 것)가 끝나는 때. UTC 다."""
    certificate = x509.load_pem_x509_certificate(pem)
    # cryptography 42 부터 not_valid_after_utc 가 있다. 그 전 판은 시간대가 없는 UTC 를 준다
    after = getattr(certificate, 'not_valid_after_utc', None)
    if after is None:
        after = certificate.not_valid_after.replace(tzinfo=datetime.UTC)
    return after


def days_left(pem: bytes, now: datetime.datetime) -> float:
    """끝날 때까지 남은 날. 지났으면 0 보다 작다."""
    return (expires_at(pem) - now).total_seconds() / 86400


def is_fresh(pem: bytes, now: datetime.datetime, min_days: int = MIN_DAYS_LEFT) -> bool:
    """남은 날이 충분한가."""
    return days_left(pem, now) >= min_days


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else CERT_PATH
    try:
        pem = path.read_bytes()
        left = days_left(pem, datetime.datetime.now(datetime.UTC))
    except (OSError, ValueError) as error:
        print(f'인증서를 읽지 못했다({path}): {error}', file=sys.stderr)
        return 1
    if left < MIN_DAYS_LEFT:
        print(f'인증서가 {left:.1f}일 남았다. 갱신이 실패하고 있다(docker compose logs certbot)', file=sys.stderr)
        return 1
    print(f'인증서가 {left:.1f}일 남았다')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
