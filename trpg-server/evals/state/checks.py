# trpg-server/evals/state/checks.py

"""
서술 하나를 기계로 검사하는 것들. 순수 함수다. 모델도 DB 도 모른다.

검사는 넷이다.
  - Forbid:   이 낱말이 나오면 걸린다. 엔진이 정한 것을 뒤집거나(실패를 성공으로), 숨긴 것을 흘렸을 수 있다
  - Require:  이 낱말 중 하나도 안 나오면 걸린다. 엔진이 정한 것(부상, 치료의 결과)을 빠뜨렸을 수 있다
  - Pattern:  이 모양(정규식)의 글이 나오면 걸린다. 낱말로 적을 수 없는 것(시각의 숫자)에 쓴다
  - NoSpeech: 따옴표 속 글이 있으면 걸린다. 장면의 NPC 가 모두 말할 수 없는(쓰러진, 죽은) 장면에 쓴다.
              PC 는 말도 소리도 따옴표로 쓰지 않는다(narration-5). 의식이 없는 NPC 는 신음도 못 낸다.
              그래서 그런 장면의 따옴표 속 글은 짧은 소리까지 모두 어긴 것이다(try_narration 은 짧은 소리를 뺀다)
낱말로 어림하는 검사다. 걸렸다고 틀린 것은 아니고, 안 걸렸다고 맞은 것도 아니다. 걸린 장면은 사람이 읽는다.

따옴표를 찾는 법은 scripts/try_narration.py 의 것을 그대로 쓴다. 두 도구가 같은 따옴표를 같게 찾는다.
"""

import re
from dataclasses import dataclass
from typing import Protocol

from scripts.try_narration import QUOTE

# 한국어 장면에 섞여 들면 안 되는 글자와, 쓰지 말라고 한 마크다운
HANZI = re.compile(r'[一-鿿]')
LATIN_WORD = re.compile(r'[A-Za-z]{3,}')
MARKDOWN = re.compile(r'\*\*|^#+ |^\s*[-*] ', re.MULTILINE)
NUMBER = re.compile(r'\d+')
# 걸린 따옴표 속 말을 보여 줄 때의 길이
EVIDENCE_LENGTH = 30


class Check(Protocol):
    """서술 하나를 보는 검사. 걸린 근거를 돌려준다. 비어 있으면 통과다."""

    label: str

    def violations(self, scene: str) -> list[str]: ...


@dataclass(frozen=True)
class Forbid:
    """이 낱말이 하나라도 나오면 걸린다. 근거는 나온 낱말들이다."""

    label: str
    words: tuple[str, ...]

    def violations(self, scene: str) -> list[str]:
        return [word for word in self.words if word in scene]


@dataclass(frozen=True)
class Require:
    """이 낱말이 하나도 안 나오면 걸린다. 근거는 '없음' 한 줄이다."""

    label: str
    words: tuple[str, ...]

    def violations(self, scene: str) -> list[str]:
        if any(word in scene for word in self.words):
            return []
        return [f'{"/".join(self.words)} 없음']


@dataclass(frozen=True)
class Pattern:
    """이 모양의 글이 하나라도 나오면 걸린다. 근거는 나온 글들이다(나온 순서, 같은 것은 한 번)."""

    label: str
    pattern: re.Pattern[str]

    def violations(self, scene: str) -> list[str]:
        return list(dict.fromkeys(match.group() for match in self.pattern.finditer(scene)))


@dataclass(frozen=True)
class NoSpeech:
    """따옴표 속 글이 있으면 걸린다. 짧은 소리(윽, 쿵)도 센다. 근거는 그 글들이다(앞부분만)."""

    label: str

    def violations(self, scene: str) -> list[str]:
        return [body[:EVIDENCE_LENGTH] for body in QUOTE.findall(scene)]


@dataclass(frozen=True)
class Finding:
    """검사 하나의 결과. evidence 가 비어 있으면 통과다."""

    label: str
    evidence: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.evidence


def run_checks(scene: str, checks: tuple[Check, ...]) -> tuple[Finding, ...]:
    """모든 검사를 돌린다. 검사의 차례대로다."""
    return tuple(Finding(check.label, tuple(check.violations(scene))) for check in checks)


def made_up_numbers(scene: str, prompt: str) -> list[str]:
    """장면의 숫자 중 보낸 프롬프트에 없는 것. 작은 것부터."""
    sent = set(NUMBER.findall(prompt))
    return sorted(set(NUMBER.findall(scene)) - sent, key=int)


def general_hints(scene: str, prompt: str) -> list[str]:
    """
    어느 장면에나 보는 의심거리. 보낸 적 없는 숫자, 한자, 영어 낱말, 마크다운.

    검사(Check)와 달리 세어서 표에 넣지 않는다. 장면 옆에 적어 사람이 본다.
    """
    hints = []
    numbers = made_up_numbers(scene, prompt)
    if numbers:
        hints.append(f'보낸 적 없는 숫자({", ".join(numbers)})')
    hanzi = HANZI.findall(scene)
    if hanzi:
        hints.append(f'한자 {len(hanzi)}자')
    latin = LATIN_WORD.findall(scene)
    if latin:
        hints.append(f'영어 낱말 {len(latin)}개')
    if MARKDOWN.search(scene):
        hints.append('마크다운')
    return hints
