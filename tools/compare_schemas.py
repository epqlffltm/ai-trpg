# tools/compare_schemas.py

"""
같은 DB 의 두 스키마가 같은 모양인지 pg_dump 로 견준다(#1273, 마이그레이션 기준선).

기준선을 만들 때 옛 사슬로 올린 스키마와 기준선으로 올린 스키마가 같다는 것을 보이는 데 쓴다.
옛 사슬은 기준선을 머지하면 저장소에서 사라지므로, 이 비교는 기준선마다 한 번 하고 결과를 PR 에 적는다.

    사용: python3 tools/compare_schemas.py --dsn postgresql://postgres@127.0.0.1:5432/trpg asset_old asset_new

견주는 것은 둘이다.
  - 모양(pg_dump --schema-only): 표, 칸, 제약, 색인, 함수, 트리거
  - 넣어 둔 줄(pg_dump --data-only): 빈 스키마에 마이그레이션이 넣은 줄
어디까지 적용했는지 적는 표(alembic_version)와, 소유자·권한, pg_dump 의 머리말은 빼고 견준다. 스키마 이름도 지운다.
표의 칸의 차례는 따로 알린다. 옛 사슬은 칸을 뒤에 덧붙여 차례가 다르다. 칸의 이름으로 읽는 코드에는 상관없다.

차례만 다르면 0 으로, 그 밖이 다르면 다른 줄을 찍고 1 로 끝난다. pg_dump 가 있어야 한다. 표준 라이브러리만 쓴다.
"""

import argparse
import difflib
import re
import subprocess
import sys

# 머리말과 연결의 설정. 덤프마다 달라 견주지 않는다
NOISE = re.compile(r'^(--|SET |SELECT pg_catalog\.set_config|\\restrict |\\unrestrict )')
VERSION_TABLE = 'alembic_version'


def dump(dsn: str, schema: str, *, data: bool) -> str:
    """스키마 하나의 덤프. data 면 넣어 둔 줄, 아니면 모양이다."""
    part = '--data-only' if data else '--schema-only'
    command = [
        'pg_dump', '--dbname', dsn, part, '--no-owner', '--no-privileges',
        '--schema', schema, '--exclude-table', f'{schema}.{VERSION_TABLE}',
    ]  # fmt: skip
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def cleaned(text: str, schema: str) -> list[str]:
    """견줄 줄들. 머리말과 빈 줄을 빼고 스키마 이름을 지운다."""
    pattern = re.compile(rf'\b{re.escape(schema)}\b')
    return [pattern.sub('SCHEMA', line) for line in text.splitlines() if line.strip() and not NOISE.match(line)]


def is_column(line: str) -> bool:
    """CREATE TABLE 안의 칸 한 줄인가."""
    return line.startswith('    ') and not line.lstrip().startswith(')')


def without_column_order(lines: list[str]) -> list[str]:
    """CREATE TABLE 안의 칸들을 이름의 차례로 놓는다. 끝의 쉼표는 뗀다. 그 밖의 줄은 그대로다."""
    result: list[str] = []
    columns: list[str] = []
    inside = False
    for line in lines:
        if inside and is_column(line):
            columns.append(line.rstrip(','))
            continue
        if inside:
            result.extend(sorted(columns))
            columns, inside = [], False
        result.append(line)
        inside = line.startswith('CREATE TABLE ')
    return [*result, *sorted(columns)]


COPY_HEAD = re.compile(r'^COPY (?P<table>\S+) \((?P<columns>[^)]*)\) FROM stdin;$')


def rows_by_name(lines: list[str]) -> list[str]:
    """
    넣어 둔 줄을 칸의 이름으로 적은 줄들로 바꾼다. 표와 줄의 차례로 놓는다.

    pg_dump 는 COPY 의 머리에 칸을 표의 차례로 적는다. 칸의 차례가 다른 두 스키마도 같은 줄이면 같게 나온다.
    """
    result: list[str] = []
    table, columns = '', []
    for line in lines:
        head = COPY_HEAD.match(line)
        if head:
            table, columns = head['table'], [name.strip() for name in head['columns'].split(',')]
        elif line == '\\.':
            table, columns = '', []
        elif table:
            pairs = sorted(zip(columns, line.split('\t'), strict=True))
            result.append(f'{table}: ' + ', '.join(f'{name}={value}' for name, value in pairs))
        else:
            result.append(line)
    return sorted(result)


def differences(old: list[str], new: list[str]) -> list[str]:
    """두 줄 목록의 다른 곳. 같으면 빈 목록이다."""
    return [line for line in difflib.unified_diff(old, new, 'old', 'new', lineterm='') if line]


def compare(old: list[str], new: list[str]) -> tuple[list[str], bool]:
    """칸의 차례를 빼고 다른 곳과, 칸의 차례만 다른가."""
    found = differences(without_column_order(old), without_column_order(new))
    return found, not found and old != new


def report(name: str, found: list[str], order_only: bool) -> None:
    """견준 결과 하나를 찍는다."""
    if found:
        print(f'{name}: 다르다', file=sys.stderr)
        print('\n'.join(found), file=sys.stderr)
    elif order_only:
        print(f'{name}: 같다(표의 칸의 차례만 다르다)')
    else:
        print(f'{name}: 같다')


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description='같은 DB 의 두 스키마를 pg_dump 로 견준다')
    parser.add_argument('--dsn', required=True, help='DB 의 주소(libpq). 두 스키마를 모두 읽을 수 있는 계정')
    parser.add_argument('old', help='옛 사슬로 올린 스키마')
    parser.add_argument('new', help='기준선으로 올린 스키마')
    args = parser.parse_args(argv)
    failed = False
    for name, data in (('모양', False), ('넣어 둔 줄', True)):
        old = cleaned(dump(args.dsn, args.old, data=data), args.old)
        new = cleaned(dump(args.dsn, args.new, data=data), args.new)
        found, order_only = compare(rows_by_name(old), rows_by_name(new)) if data else compare(old, new)
        report(name, found, order_only)
        failed = failed or bool(found)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
