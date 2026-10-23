# auth-server/accounts/db_fields.py

"""
Django 에 없는 DB 의 칸.

CidrField 는 PostgreSQL 의 cidr(IP 주소의 대역)이다. 주소 하나도 /32(IPv4), /128(IPv6) 대역으로 담는다.
"이 주소가 그 대역 안에 드는가"를 DB 가 한 번에 본다(net_contains_or_equals, PostgreSQL 의 >>=).
파이썬 쪽 값은 ipaddress 의 IPv4Network, IPv6Network 다.
"""

import ipaddress

from django.db import models
from django.db.models import Lookup

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class CidrField(models.Field):
    """PostgreSQL 의 cidr. 대역의 뒤쪽 비트가 0 이 아닌 값은 DB 가 받지 않는다(넣기 전에 맞춘다)."""

    description = 'IP 주소의 대역(PostgreSQL cidr)'

    def db_type(self, connection) -> str:
        return 'cidr'

    def from_db_value(self, value, expression, connection) -> Network | None:
        """DB 의 값을 대역으로. 드라이버가 글이나 대역 어느 쪽으로 주든 같은 것이 된다."""
        return None if value is None else ipaddress.ip_network(str(value))

    def to_python(self, value) -> Network | None:
        if value is None or isinstance(value, ipaddress.IPv4Network | ipaddress.IPv6Network):
            return value
        return ipaddress.ip_network(str(value))

    def get_prep_value(self, value) -> str | None:
        """DB 에 넣을 글. 1.2.3.0/24 꼴이다."""
        return None if value is None else str(self.to_python(value))


@CidrField.register_lookup
class NetContainsOrEquals(Lookup):
    """
    칸의 대역이 오른쪽의 주소(또는 대역)를 담거나 같은가. PostgreSQL 의 >>= 다.

    오른쪽은 주소의 글(203.0.113.7)이다. 칸의 값으로 바꾸지 않고 그대로 inet 으로 넘긴다.
    """

    lookup_name = 'net_contains_or_equals'
    prepare_rhs = False

    def get_db_prep_lookup(self, value, connection):
        return '%s', [str(value)]

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        return f'{lhs} >>= {rhs}::inet', [*lhs_params, *rhs_params]
