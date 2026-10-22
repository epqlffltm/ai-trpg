# tools/test_model_slugs.py

"""
판매가 파일의 가격 코드와 모델 목록의 이름표가 어긋나지 않는지 보는 도구(model_slugs.py)를 본다.

    사용: python3 -m unittest discover -s tools -p 'test_model_slugs.py'

저장소의 진짜 파일 둘도 여기서 맞춰 본다. 어느 한쪽을 고친 PR 이 다른 쪽과 어긋나면 실패한다.
"""

import tempfile
import unittest
from pathlib import Path

from model_slugs import CATALOG, DOCS, WAITING, catalog_slugs, latest_price_file, priced_slugs, unknown_slugs

CATALOG_TEXT = """
format = 1

[[models]]
slug = "gpt-6-luna"

[[models]]
slug = "glm-4-7-flash"
"""

PRICES_TEXT = """code,credits,effective_at,tier
# 값 줄이 아닌 것
narration.gpt-6-luna.i0.o0,20,,standard
narration.gpt-6-luna.i1.o2,40,,standard
narration.standard,50,,
attendance.daily,10,,

narration.claude-opus-5-5.i0.o0,420,,premium
chat.gemini-3-6-flash.i0.o0,80,,standard
"""


class ModelSlugsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.catalog = self.root / 'model_catalog.toml'
        self.catalog.write_text(CATALOG_TEXT, encoding='utf-8')
        self.docs = self.root / 'docs'
        self.docs.mkdir()

    def write_prices(self, name: str, text: str = PRICES_TEXT) -> Path:
        path = self.docs / name
        path.write_text(text, encoding='utf-8')
        return path

    def test_only_model_codes_with_steps_count(self):
        path = self.write_prices('model-prices-2026-10-18-v3.csv')

        # 서버마다 머리가 다르다(chat 서버는 chat). 모델이 아닌 것과 단계가 없는 옛 코드는 보지 않는다
        self.assertEqual(priced_slugs(path), {'gpt-6-luna', 'claude-opus-5-5', 'gemini-3-6-flash'})

    def test_a_price_without_a_model_is_found(self):
        self.write_prices('model-prices-2026-10-18-v3.csv')

        # 판매가가 없는 모델(glm-4-7-flash)은 된다
        self.assertEqual(unknown_slugs(self.catalog, self.docs), ['claude-opus-5-5', 'gemini-3-6-flash'])

    def test_the_latest_price_file_is_the_one_read(self):
        self.write_prices('model-prices-2026-10-18-v2.csv')
        self.write_prices('model-prices-2026-10-18-v3.csv', 'code,credits\nnarration.gpt-6-luna.i0.o0,20\n')
        self.write_prices('notes.csv', 'code\nnarration.nothing.i0.o0\n')

        self.assertEqual(latest_price_file(self.docs).name, 'model-prices-2026-10-18-v3.csv')
        self.assertEqual(unknown_slugs(self.catalog, self.docs), [])

    def test_waiting_slugs_are_left_out(self):
        self.write_prices('model-prices-2026-10-18-v3.csv')

        self.assertEqual(unknown_slugs(self.catalog, self.docs, frozenset({'claude-opus-5-5'})), ['gemini-3-6-flash'])

    def test_no_price_file_finds_nothing(self):
        self.assertEqual(unknown_slugs(self.catalog, self.docs), [])

    def test_the_repository_files_agree(self):
        self.assertIsNotNone(latest_price_file(DOCS))
        self.assertEqual(unknown_slugs(CATALOG, DOCS, frozenset(WAITING)), [])

    def test_the_waiting_slugs_are_still_waiting(self):
        # 모델 목록에 넣었거나 판매가에서 빠졌으면 WAITING 에서 지운다
        self.assertEqual(set(WAITING) & catalog_slugs(CATALOG), set())
        self.assertEqual(set(WAITING) - priced_slugs(latest_price_file(DOCS)), set())


if __name__ == '__main__':
    unittest.main()
