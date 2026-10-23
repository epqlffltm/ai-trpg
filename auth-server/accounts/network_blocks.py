# auth-server/accounts/network_blocks.py

"""
IP 주소나 대역으로 가입, 로그인, 토큰 갱신을 막는다(#638).

불법 행위로 정지한 사람은 새 계정과 새 이메일로 돌아올 수 있다. 본인인증과 이메일의 값(return_blocks.py)으로는
막지 못한다. 운영자가 그 사람의 IP 나 대역을 기간과 함께 적으면, 그 주소에서 온 가입, 로그인, 토큰 갱신을 거절한다.
다른 서버는 인증 서버가 준 토큰으로만 쓰므로, 액세스 토큰이 끝나면 모든 서버에서 끊긴다.

  - 주소 하나를 적으면 IPv4 는 그 주소(/32), IPv6 는 가입자 한 집이 받는 묶음(/64)을 막는다(client_ip 의 묶음과 같다)
  - 대역은 IPv4 /16, IPv6 /32 보다 넓게 적지 못한다. 실수로 많은 사람을 막지 않게 한다
  - 늘 푸는 시각이 있다. 기본 30일, 길어야 365일. IP 는 바뀌고 남에게 넘어간다
  - 막힌 사람에게는 막혔다고 알린다(views.build_network_blocked_response). 학교나 회사처럼 IP 를 함께 쓰는 곳의
    다른 사람이 까닭을 알고 문의할 수 있게 한다. 막힌 쪽은 IP 를 바꾸면 되므로 숨겨서 얻는 것이 적다
  - 기간이 지난 줄은 막지 않고, 정리(send_security_digest)가 지운다

대량의 요청(서비스 공격)은 여기서 막지 않는다. 클라우드의 방화벽이 맡는다.
"""

import ipaddress
import logging
from datetime import datetime, timedelta

from accounts.db_fields import Network
from accounts.models import NetworkBlock

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 30
MAX_DAYS = 365
# 주소 하나를 적었을 때 막는 크기
IPV4_SINGLE_PREFIX = 32
IPV6_SINGLE_PREFIX = 64
# 적을 수 있는 가장 넓은 대역. 이보다 짧은 접두어(더 넓은 대역)는 받지 않는다
IPV4_WIDEST_PREFIX = 16
IPV6_WIDEST_PREFIX = 32


class InvalidNetworkError(ValueError):
    """주소나 대역이 아니거나 너무 넓다."""


class InvalidDaysError(ValueError):
    """막는 기간이 1~MAX_DAYS 일이 아니다."""


def parse_network(text: str) -> Network:
    """
    운영자가 적은 주소나 대역을 막을 대역으로 바꾼다. 못 쓰면 InvalidNetworkError.

    대역의 뒤쪽 비트는 0 으로 맞춘다(1.2.3.4/24 → 1.2.3.0/24). IPv4 를 IPv6 로 적은 것(::ffff:1.2.3.4)은 IPv4 로 본다.
    """
    value = text.strip()
    try:
        network = _as_network(value)
    except ValueError as exc:
        raise InvalidNetworkError('IP 주소나 대역(1.2.3.0/24 꼴)을 적어 주세요.') from exc
    widest = IPV4_WIDEST_PREFIX if network.version == 4 else IPV6_WIDEST_PREFIX
    if network.prefixlen < widest:
        raise InvalidNetworkError(f'IPv{network.version} 는 /{widest} 보다 넓게 막지 않습니다.')
    return network


def _as_network(value: str) -> Network:
    """주소면 한 사람의 크기로, 대역이면 그대로 대역으로."""
    if '/' in value:
        network = ipaddress.ip_network(value, strict=False)
        mapped = network.network_address.ipv4_mapped if network.version == 6 else None
        if mapped is not None:
            return ipaddress.ip_network(f'{mapped}/{max(network.prefixlen - 96, 0)}', strict=False)
        return network
    address = ipaddress.ip_address(value)
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    prefix = IPV4_SINGLE_PREFIX if address.version == 4 else IPV6_SINGLE_PREFIX
    return ipaddress.ip_network(f'{address}/{prefix}', strict=False)


def clean_days(days: int) -> int:
    """막는 기간(일)을 확인한다. 1~MAX_DAYS 가 아니면 InvalidDaysError."""
    if not 1 <= days <= MAX_DAYS:
        raise InvalidDaysError(f'기간은 1~{MAX_DAYS}일입니다.')
    return days


def block_network(network: Network, days: int, note: str, now: datetime) -> tuple[NetworkBlock, bool]:
    """
    그 대역을 막는다. 새로 막았으면 (줄, True), 이미 있으면 기간과 사유를 이번 것으로 바꾸고 (줄, False).

    다시 적는 것은 운영자가 새로 정한 것이다. 앞의 것보다 짧아질 수도 있다.
    """
    block, created = NetworkBlock.objects.update_or_create(
        network=network,
        defaults={'note': note, 'expires_at': now + timedelta(days=days)},
    )
    return block, created


def unblock_network(network: Network) -> bool:
    """그 대역의 막기를 지운다. 지운 것이 있으면 True."""
    deleted, _ = NetworkBlock.objects.filter(network=network).delete()
    return deleted > 0


def find_block(client_ip: str, now: datetime) -> NetworkBlock | None:
    """
    그 주소를 담은 살아 있는 막기. 없으면 None.

    주소가 아닌 글(프록시 설정이 어긋나 REMOTE_ADDR 가 빈 것 같은)이면 막지 않는다. 막기 때문에 서버가 멈추지 않게 한다.
    """
    try:
        ipaddress.ip_address(client_ip)
    except ValueError:
        return None
    return NetworkBlock.objects.filter(expires_at__gt=now, network__net_contains_or_equals=client_ip).first()


def log_blocked_request(block: NetworkBlock, path: str) -> None:
    """
    막은 대역에서 온 요청을 거절했다고 로그에 남긴다. 어느 막기에 걸렸는지(줄의 번호)만 적는다.

    DB 의 보안 이벤트로는 남기지 않는다. 막힌 쪽이 요청을 되풀이하면 그만큼 행이 쌓인다. 수는 메트릭이 센다.
    """
    logger.info('막은 대역에서 온 요청을 거절했다. block=%s path=%s', block.pk, path)


def delete_expired_network_blocks(now: datetime) -> int:
    """기간이 지난 막기를 지우고, 지운 수를 돌려준다."""
    deleted, _ = NetworkBlock.objects.filter(expires_at__lte=now).delete()
    return deleted
