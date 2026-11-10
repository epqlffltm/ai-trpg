# tools/test_compare_schemas.py

"""
두 스키마를 견주는 도구(compare_schemas.py)의 규칙을 본다. DB 와 pg_dump 없이 덤프의 글자로만 본다.

    사용: python3 -m unittest discover -s tools -p 'test_*.py'
"""

import unittest

from compare_schemas import cleaned, compare, rows_by_name, without_column_order

OLD_SCHEMA = """--
-- PostgreSQL database dump
--
\\restrict abc
SET statement_timeout = 0;
SELECT pg_catalog.set_config('search_path', '', false);

CREATE TABLE asset_old.images (
    id uuid NOT NULL,
    format character varying(10) NOT NULL,
    kept_by character varying(32)
);
CREATE INDEX ix_images_owner ON asset_old.images USING btree (id);
\\unrestrict abc
"""


class CleanTests(unittest.TestCase):
    def test_noise_and_the_schema_name_go_away(self):
        self.assertEqual(
            cleaned(OLD_SCHEMA, 'asset_old'),
            [
                'CREATE TABLE SCHEMA.images (',
                '    id uuid NOT NULL,',
                '    format character varying(10) NOT NULL,',
                '    kept_by character varying(32)',
                ');',
                'CREATE INDEX ix_images_owner ON SCHEMA.images USING btree (id);',
            ],
        )

    def test_only_the_whole_schema_name_is_replaced(self):
        self.assertEqual(
            cleaned('SELECT asset_old_x FROM asset_old.t;', 'asset_old'),
            [
                'SELECT asset_old_x FROM SCHEMA.t;',
            ],
        )


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.old = cleaned(OLD_SCHEMA, 'asset_old')

    def test_the_same_dump_is_the_same(self):
        self.assertEqual(compare(self.old, list(self.old)), ([], False))

    def test_a_different_column_order_is_told_apart_from_a_difference(self):
        new = [
            'CREATE TABLE SCHEMA.images (',
            '    kept_by character varying(32),',
            '    id uuid NOT NULL,',
            '    format character varying(10) NOT NULL',
            ');',
            'CREATE INDEX ix_images_owner ON SCHEMA.images USING btree (id);',
        ]

        self.assertEqual(compare(self.old, new), ([], True))

    def test_a_missing_index_is_a_difference(self):
        found, order_only = compare(self.old, self.old[:-1])

        self.assertIn('-CREATE INDEX ix_images_owner ON SCHEMA.images USING btree (id);', found)
        self.assertFalse(order_only)

    def test_a_changed_column_is_a_difference(self):
        new = [line.replace('varying(10)', 'varying(20)') for line in self.old]

        self.assertNotEqual(compare(self.old, new)[0], [])

    def test_columns_are_sorted_only_inside_a_table(self):
        lines = ['CREATE TABLE SCHEMA.t (', '    b int,', '    a int', ');', '    z stays', '    y stays']

        self.assertEqual(without_column_order(lines), [
            'CREATE TABLE SCHEMA.t (', '    a int', '    b int', ');', '    z stays', '    y stays',
        ])  # fmt: skip


class RowsTests(unittest.TestCase):
    def test_rows_are_named_by_column_so_the_order_does_not_matter(self):
        old = ['COPY SCHEMA.boards (id, name) FROM stdin;', '1\tfree', '\\.']
        new = ['COPY SCHEMA.boards (name, id) FROM stdin;', 'free\t1', '\\.']

        self.assertEqual(rows_by_name(old), rows_by_name(new))
        self.assertEqual(rows_by_name(old), ['SCHEMA.boards: id=1, name=free'])

    def test_a_missing_row_is_a_difference(self):
        old = rows_by_name(['COPY SCHEMA.boards (id, name) FROM stdin;', '1\tfree', '2\tnotice', '\\.'])
        new = rows_by_name(['COPY SCHEMA.boards (id, name) FROM stdin;', '1\tfree', '\\.'])

        self.assertNotEqual(compare(old, new)[0], [])

    def test_lines_outside_copy_stay(self):
        lines = ["SELECT pg_catalog.setval('SCHEMA.s', 1, false);"]

        self.assertEqual(rows_by_name(lines), lines)


if __name__ == '__main__':
    unittest.main()
