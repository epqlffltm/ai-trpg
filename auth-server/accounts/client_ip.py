# auth-server/accounts/client_ip.py

"""
요청을 보낸 쪽의 IP 주소를 알아낸다. 시도 횟수를 IP 별로 세는 데 쓴다.

서버에 직접 연결한 상대의 주소(REMOTE_ADDR)는 믿을 수 있다. 그런데 배포하면
서버 앞에 프록시(nginx, 로드밸런서)가 서고, 모든 요청의 REMOTE_ADDR 가 프록시의 주소가 된다.
프록시는 원래 주소를 X-Forwarded-For 헤더에 적어 넘긴다.

그 헤더는 요청을 보내는 쪽도 마음대로 적어 보낼 수 있다. 그대로 믿으면
요청마다 다른 주소를 적어 IP 별 제한을 통째로 피할 수 있다.
그래서 "우리 프록시가 적은 부분" 만 믿는다.
"""

import ipaddress

from django.conf import settings
from django.http import HttpRequest

# IPv6 는 가입자 한 명에게 주소가 통째로 한 묶음(/64, 약 1800경 개) 배정된다.
# 주소 하나하나를 따로 세면 주소를 바꿔 가며 제한을 피할 수 있다. 묶음 단위로 센다
IPV6_GROUP_PREFIX = 64


def get_client_ip(request: HttpRequest) -> str:
    """
    요청을 보낸 쪽의 IP 주소를 돌려준다.

    TRUSTED_PROXY_COUNT 가 0 이면 서버에 직접 연결한 상대의 주소다. 헤더는 보지 않는다.
    1 이상이면 X-Forwarded-For 의 뒤에서 그만큼 센 자리의 주소다.
    """
    remote_addr = request.META.get('REMOTE_ADDR', '')
    proxy_count = settings.TRUSTED_PROXY_COUNT
    if proxy_count == 0:
        return _normalize(remote_addr) or remote_addr

    forwarded = _read_forwarded_for(request)
    if len(forwarded) < proxy_count:
        # 프록시를 거쳤다면 있어야 할 만큼의 주소가 없다.
        # 프록시를 건너뛰고 서버에 직접 온 요청이거나 설정이 실제 구조와 다르다.
        # 헤더를 믿지 않고 직접 연결한 상대의 주소를 쓴다
        return _normalize(remote_addr) or remote_addr

    return _normalize(forwarded[-proxy_count]) or _normalize(remote_addr) or remote_addr


def get_attempt_subject(request: HttpRequest) -> str:
    """
    시도 횟수를 셀 때 "같은 곳" 으로 볼 단위를 돌려준다.

    IPv4 는 주소 그대로, IPv6 는 앞 64비트가 같은 주소를 한 곳으로 본다.
    """
    client_ip = get_client_ip(request)
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return client_ip
    if address.version == 4:
        return str(address)
    network = ipaddress.ip_network(f'{address}/{IPV6_GROUP_PREFIX}', strict=False)
    return str(network)


def _read_forwarded_for(request: HttpRequest) -> list[str]:
    """
    X-Forwarded-For 의 주소들을 순서대로 돌려준다.

    프록시를 지날 때마다 뒤에 주소가 하나씩 붙는다. 프록시는 자기에게 연결한 상대의 주소를 붙인다.
    그래서 앞쪽은 요청을 보낸 쪽이 지어낼 수 있고, 뒤쪽은 우리 프록시가 적은 것이다.
    """
    header = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return [part.strip() for part in header.split(',') if part.strip()]


def _normalize(value: str) -> str:
    """
    IP 주소를 한 가지 표기로 통일한다. 주소가 아니면 빈 문자열을 돌려준다.

    같은 주소가 표기만 달라 따로 세어지는 것을 막는다.
    IPv4 주소를 IPv6 형태로 적은 것(::ffff:1.2.3.4)은 IPv4 로 되돌린다.
    """
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return ''
    if address.version == 6 and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return str(address)
