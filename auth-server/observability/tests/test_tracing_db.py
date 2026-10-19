# auth-server/observability/tests/test_tracing_db.py

"""
쿼리마다 span 이 걸리는지 실제 DB 로 검증한다(observability/db_spans.py).
"""

from django.db import DatabaseError, connection, transaction
from django.test import SimpleTestCase, TestCase
from opentelemetry.trace import SpanKind, StatusCode

from accounts.models import User
from observability.db_spans import (
    instrument_connection,
    operation_of,
    query_span_name,
    sql_state,
    table_of,
    trace_query,
)
from observability.tests.spans import record_spans

# 값을 흉내 낸다. span 에 실리면 안 된다
SECRET_EMAIL = 'secret-person@example.com'


class QuerySpanTests(TestCase):
    def setUp(self) -> None:
        self.spans = record_spans(self)

    def test_a_query_under_a_span_gets_a_span_named_by_its_table(self):
        with self.spans.parent() as parent:
            list(User.objects.filter(email=SECRET_EMAIL))

        span = self.spans.find('db SELECT accounts_user')
        self.assertEqual(span.kind, SpanKind.CLIENT)
        self.assertEqual(span.parent.span_id, parent.get_span_context().span_id)
        self.assertEqual(span.attributes['db.system.name'], 'postgresql')
        self.assertEqual(span.attributes['db.operation.name'], 'SELECT')
        self.assertEqual(span.attributes['db.collection.name'], 'accounts_user')
        # 문장과 값은 싣지 않는다
        self.assertNotIn(SECRET_EMAIL, str(dict(span.attributes)))
        self.assertNotIn('WHERE', str(dict(span.attributes)))

    def test_a_change_is_named_by_the_table_it_changes(self):
        with self.spans.parent():
            User.objects.filter(email=SECRET_EMAIL).update(is_active=False)

        self.spans.find('db UPDATE accounts_user')

    def test_a_query_without_a_parent_gets_no_span(self):
        list(User.objects.filter(email=SECRET_EMAIL))

        self.assertEqual(self.spans.names(), [])

    def test_a_failed_query_records_only_its_sql_state(self):
        with self.spans.parent() as parent:
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SELECT 1 / 0 WHERE 'secret-value' = %s", ['secret-value'])
            self.assertTrue(parent.is_recording())

        span = self.spans.find('db SELECT')
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.status.description, '22012')
        self.assertEqual(span.events, ())
        self.assertNotIn('secret-value', str(dict(span.attributes)))

    def test_instrumenting_twice_does_not_double_the_spans(self):
        instrument_connection(connection)
        instrument_connection(connection)

        with self.spans.parent():
            list(User.objects.filter(email=SECRET_EMAIL))

        self.assertEqual(self.spans.names(), ['db SELECT accounts_user'])
        self.assertEqual(connection.execute_wrappers.count(trace_query), 1)


class StatementTests(SimpleTestCase):
    def test_the_operation_is_the_first_word(self):
        cases = {
            'select 1': 'SELECT',
            '  DELETE FROM x': 'DELETE',
            '': 'QUERY',
            '(SELECT 1)': 'QUERY',
            'A' * 17: 'QUERY',
        }
        for sql, operation in cases.items():
            with self.subTest(sql=sql):
                self.assertEqual(operation_of(sql), operation)

    def test_the_table_is_the_first_one_named(self):
        cases = {
            'SELECT "accounts_user"."id" FROM "accounts_user" WHERE 1': 'accounts_user',
            'INSERT INTO "accounts_mail" ("a") VALUES (1)': 'accounts_mail',
            'UPDATE accounts_user SET x = 1': 'accounts_user',
            'SELECT 1': None,
            'SAVEPOINT "s1"': None,
        }
        for sql, table in cases.items():
            with self.subTest(sql=sql):
                self.assertEqual(table_of(sql), table)
        self.assertEqual(query_span_name('SELECT', None), 'db SELECT')

    def test_the_sql_state_is_the_code_only(self):
        inner = Exception('user-0b9f5e0c 이 이미 있다')
        inner.sqlstate = '23505'
        outer = Exception('감쌌다')
        outer.__cause__ = inner

        self.assertEqual(sql_state(outer), '23505')
        self.assertEqual(sql_state(ConnectionError('끊겼다')), 'error')
        self.assertEqual(sql_state(None), 'error')
