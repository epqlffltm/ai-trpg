# story-server/app/turns/segments.py

"""
모델의 답을 말 조각으로 나눈다(docs/architecture/story.md 의 "한 번의 말"). DB 도 모델도 모른다.

모델은 줄마다 머리에 말하는 사람의 표식을 적는다.

    @narration: 해가 기울고 있었다.
    @mina: 늦었네. 기다렸어.
    @jun: 나도 방금 왔어.

  - 표식의 이름은 장면의 인물의 id 나 이름, 또는 서술(narration, 서술)이다(speaker_labels).
  - 장면에 없는 인물의 줄은 버리고 센다(dropped). 화면에 보이지 않고 저장하지 않는다.
  - 표식을 어긴 줄(@ 로 시작하지 않는다, 이름이 비었다, : 가 없다)은 서술로 돌린다.
  - 한 줄이 조각 하나다. 빈 줄은 버린다. 같은 사람이 이어 말해도 줄마다 조각이다(화면이 묶는다).

흘러오는 대로 자른다(SpeakerSplitter). 줄의 머리를 다 받기 전에는 그 줄의 글을 내보내지 않는다.
표식이 정해지면 그 뒤의 글은 받는 대로 내보낸다. 이름표가 스트리밍 중에 바로 바뀐다.
다 받은 답을 한 번에 나눌 때(split_segments)도 같은 것을 쓴다. 흘려보낸 것과 저장한 것이 어긋나지 않는다.

이어서 출력(continuing_splitter)은 끊긴 답의 조각들(base)에서 시작한다.
  - 첫 줄에 표식이 없으면(표식을 어긴 줄도) 끊긴 마지막 조각을 이어 쓴 것이다.
    그 조각의 글 끝에 붙이고 새 조각을 알리지 않는다.
    앞의 빈칸을 버리지 않는다(끊긴 자리의 빈칸이다)
  - 첫 줄이 표식으로 시작하면 새 조각이다. 그 뒤의 줄은 보통과 같다
  - 이어 쓴 것이 없으면 조각이 없는 것으로 돌려준다(저장할 것이 없다). 있으면 끊긴 답의 조각까지 모두 돌려준다
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

# 서술의 표식 이름들. 대소문자를 가리지 않는다
NARRATION_LABELS = frozenset({'narration', '서술'})
# 표식의 이름의 길이의 상한(글자). 이보다 길도록 : 가 없으면 표식이 아니다
LABEL_MAX_CHARS = 40
MARKER_START = '@'
MARKER_END = ':'


@dataclass(frozen=True)
class Segment:
    """말 조각 하나. speaker 는 장면의 인물의 id 이고, 서술이면 None 이다."""

    speaker: str | None
    text: str


@dataclass(frozen=True)
class SegmentStart:
    """새 조각이 시작됐다. 이 뒤의 글은 이 사람의 것이다."""

    speaker: str | None


@dataclass(frozen=True)
class SegmentText:
    """지금 조각에 붙는 글."""

    text: str


SegmentEvent = SegmentStart | SegmentText


class Dropped:
    """장면에 없는 인물의 줄. 그 줄의 글은 버린다."""


DROPPED = Dropped()


def speaker_labels(cast: Iterable[tuple[str, str]]) -> dict[str, str]:
    """
    표식의 이름 → 인물의 id. cast 는 장면의 인물들의 (id, 이름)이다. id 와 이름을 모두 받는다.

    이름이 서술의 표식과 같거나 다른 인물의 id 와 겹치면 이름으로는 받지 않는다(id 가 앞선다).
    """
    labels: dict[str, str] = {}
    pairs = list(cast)
    for cast_id, _ in pairs:
        labels[cast_id.casefold()] = cast_id
    for cast_id, name in pairs:
        key = name.strip().casefold()
        if key and key not in labels and key not in NARRATION_LABELS:
            labels[key] = cast_id
    return labels


def resolve(label: str, labels: Mapping[str, str]) -> str | None | Dropped:
    """표식의 이름이 가리키는 사람. 서술이면 None, 장면에 없는 이름이면 DROPPED."""
    key = label.strip().casefold()
    if key in NARRATION_LABELS:
        return None
    return labels.get(key, DROPPED)


@dataclass
class SpeakerSplitter:
    """
    흘러오는 글을 줄마다 말 조각으로 자른다. feed 가 내보낼 것(SegmentEvent)을 돌려준다.

    labels 는 speaker_labels 가 만든 것이다. 끝나면 finish 를 부르고 segments 와 dropped 를 읽는다.
    """

    labels: Mapping[str, str]
    # 지금 줄의 머리. 표식인지 정해지기 전까지 모은다
    head: str = ''
    # 지금 줄의 말하는 사람이 정해졌나
    decided: bool = False
    speaker: str | None | Dropped = None
    # 지금 줄의 조각을 알렸나(글이 처음 나올 때 알린다. 글 없는 줄은 조각이 아니다)
    started: bool = False
    text: str = ''
    found: list[Segment] = field(default_factory=list)
    dropped: int = 0
    # 이어서 출력의 끊긴 답의 조각들. 보통은 비어 있다
    base: tuple[Segment, ...] = ()
    # 첫 줄을 아직 받는 중이고, 표식이 없으면 끊긴 마지막 조각을 이어 쓴다(이어서 출력)
    carrying: bool = False
    # 지금 줄이 끊긴 마지막 조각을 이어 쓰는 줄이다
    extending: bool = False
    # base 뒤에 이어 쓴 것이 있다
    added: bool = False

    def feed(self, piece: str) -> list[SegmentEvent]:
        """글의 조각을 받아 내보낼 것들을 돌려준다."""
        events: list[SegmentEvent] = []
        for char in piece.replace('\r', ''):
            if char == '\n':
                self.end_line(events)
            elif self.decided:
                self.add(char, events)
            else:
                self.head += char
                self.classify(events, line_ended=False)
        return events

    def finish(self) -> list[SegmentEvent]:
        """끝났다. 남은 줄을 마저 자른다."""
        events: list[SegmentEvent] = []
        self.end_line(events)
        return events

    def segments(self) -> tuple[Segment, ...]:
        """
        지금까지 자른 조각들. finish 뒤에 읽는다.
        이어서 출력이면 끊긴 답의 조각까지 모두이고, 이어 쓴 것이 없으면 빈 것이다.
        """
        if self.base and not self.added:
            return ()
        return tuple(self.found)

    def fallback(self) -> str | None:
        """표식이 없는 줄의 말하는 사람. 보통은 서술이고, 이어서 출력의 첫 줄이면 끊긴 마지막 조각의 사람이다."""
        return self.found[-1].speaker if self.carrying else None

    def classify(self, events: list[SegmentEvent], line_ended: bool) -> None:
        """
        줄의 머리로 말하는 사람을 정한다. 아직 정할 수 없으면(표식을 받는 중) 기다린다.
        줄이 끝났는데도 정하지 못했으면 그 줄은 서술이다.
        """
        stripped = self.head.lstrip()
        if not stripped:
            return
        if not stripped.startswith(MARKER_START):
            self.decide_unmarked(stripped, events)
            return
        end = stripped.find(MARKER_END)
        if end > 1:
            self.carrying = False
            self.decide(resolve(stripped[1:end], self.labels), stripped[end + 1 :].lstrip(' '), events)
        elif end == 1 or len(stripped) > LABEL_MAX_CHARS + 1 or line_ended:
            self.decide_unmarked(stripped, events)

    def decide_unmarked(self, stripped: str, events: list[SegmentEvent]) -> None:
        """표식이 없는 줄. 보통은 서술이고, 이어서 출력의 첫 줄이면 끊긴 마지막 조각을 앞의 빈칸째 이어 쓴다."""
        if self.carrying:
            self.extending = True
            self.decide(self.fallback(), self.head, events)
        else:
            self.decide(None, stripped, events)

    def decide(self, speaker: str | None | Dropped, rest: str, events: list[SegmentEvent]) -> None:
        """이 줄의 말하는 사람을 정하고, 머리 뒤에 이미 받은 글을 붙인다."""
        self.decided = True
        self.speaker = speaker
        if speaker is DROPPED:
            self.dropped += 1
        for char in rest:
            self.add(char, events)

    def add(self, char: str, events: list[SegmentEvent]) -> None:
        """지금 줄에 글자 하나를 붙인다. 버리는 줄이면 버린다. 첫 글자 앞의 빈칸은 버린다."""
        if self.speaker is DROPPED:
            return
        if not self.started:
            if char.isspace() and not self.extending:
                return
            self.started = True
            if not self.extending:
                events.append(SegmentStart(self.speaker))
        self.text += char
        events.append(SegmentText(char))

    def end_line(self, events: list[SegmentEvent]) -> None:
        """줄이 끝났다. 조각을 남기고 다음 줄을 받을 준비를 한다."""
        if not self.decided:
            self.classify(events, line_ended=True)
        if self.started and self.text.strip():
            self.keep(Segment(self.speaker, self.text.rstrip()))
        self.head, self.decided, self.speaker, self.started, self.text = '', False, None, False, ''
        self.carrying = self.extending = False

    def keep(self, segment: Segment) -> None:
        """다 받은 줄을 남긴다. 끊긴 마지막 조각을 이어 쓴 줄이면 그 조각의 글 끝에 붙인다."""
        if self.extending:
            last = self.found[-1]
            self.found[-1] = Segment(last.speaker, last.text + segment.text)
        else:
            self.found.append(segment)
        self.added = True


def merge_events(events: Iterable[SegmentEvent]) -> list[SegmentEvent]:
    """잇닿은 글들을 하나로 묶는다. 글자마다 하나씩 보내지 않게 한다."""
    merged: list[SegmentEvent] = []
    for event in events:
        if isinstance(event, SegmentText) and merged and isinstance(merged[-1], SegmentText):
            merged[-1] = SegmentText(merged[-1].text + event.text)
        else:
            merged.append(event)
    return merged


def split_segments(text: str, labels: Mapping[str, str]) -> tuple[tuple[Segment, ...], int]:
    """다 받은 답을 조각들로. 버린 줄의 수를 함께 돌려준다."""
    splitter = SpeakerSplitter(labels)
    splitter.feed(text)
    splitter.finish()
    return splitter.segments(), splitter.dropped


def render_segments(segments: Iterable[Segment]) -> str:
    """조각들을 표식이 붙은 줄들로. 저장하는 본문이고, 다음 호출의 프롬프트에 그대로 다시 들어간다."""
    return '\n'.join(
        f'{MARKER_START}{segment.speaker or "narration"}{MARKER_END} {segment.text}' for segment in segments
    )


def segment_dicts(segments: Iterable[Segment]) -> list[dict]:
    """조각들을 저장하는 모양(JSON)으로."""
    return [{'speaker': segment.speaker, 'text': segment.text} for segment in segments]


def continuing_splitter(labels: Mapping[str, str], base: tuple[Segment, ...]) -> SpeakerSplitter:
    """끊긴 답(base)에 이어 쓰는 글을 자르는 것. 첫 줄에 표식이 없으면 끊긴 마지막 조각을 이어 쓴다."""
    return SpeakerSplitter(labels, found=list(base), base=base, carrying=bool(base))


def segments_of(dicts: Iterable[dict]) -> tuple[Segment, ...]:
    """저장한 조각들(JSON)을 조각으로."""
    return tuple(Segment(item.get('speaker'), str(item.get('text', ''))) for item in dicts)
