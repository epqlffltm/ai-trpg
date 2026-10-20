# trpg-server/app/rounds/secret_names.py

"""
아직 드러나지 않은 진짜 이름이 서술로 새지 않게 한다.

제작자는 인물 항목에 진짜 이름(true_names)을 적고, GM 메모에도 적을 수 있다. 그러면 모델은 진짜 이름을 안다.
플레이어가 맞히기 전에(app/rounds/naming.py) 모델이 장면에 그 이름을 쓰면 비밀이 샌다. 상태는 바뀌지 않아도
플레이어가 알아서는 안 되는 것을 알게 된다. 그래서 서버가 서술을 받기 전에 본다.

  - 숨길 이름(secret_names): 아직 맞히지 않은 인물의 진짜 이름들. 장면에서 대신 부를 호칭과 짝을 짓는다.
    제작자가 정답으로 적은 이름(true_names)만 숨긴다. 제작자가 고른다. 정답을 적지 않은 인물은 아무것도 숨기지 않는다.
    항목의 이름과 키워드만으로는 숨길 이름인지 알 수 없다("드워프" 에 키워드 "망치" 를 단 것은 숨기려는 것이 아니다).
    항목의 이름을 정답에 적었으면 그 이름도 숨기고 키워드로 부른다.
    키워드가 없으면 부를 이름이 그것뿐이라 숨기지 않는다.
    키워드는 장면의 호칭이라 숨기지 않는다.
    이번 라운드를 연 장면에 이미 나온 이름은 숨기지 않는다. 플레이어가 이미 읽었고(제작자의 스타팅일 수 있다),
    막으면 그 이름을 다시 쓸 때마다 서술을 버리게 된다.
  - 새었는가(leaked)와 가리기(redact): 글에 숨길 이름이 있는지, 있으면 호칭으로 바꾼 글.
  - 흘려보내는 미리 보기(GuardedPreview): 쓰이는 중인 글도 가려서 넘긴다. 조각의 끝이 숨길 이름의 앞부분일 수 있어
    그만큼은 다음 조각이 올 때까지 잡아 둔다.

한 글자 이름은 숨기지 않는다. 낱말의 한 글자와 구분할 수 없어서, 막으면 멀쩡한 서술을 버리게 된다.
DB 와 모델을 모른다. 받은 값만 본다.
"""

from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass, field

from app.assets.scenarios.snapshot import EntrySnapshot
from app.lore.retrieval import relabel
from app.rounds.narrator import Preview

# 숨길 이름에서 대신 부를 호칭으로
SecretNames = Mapping[str, str]
# 이보다 짧은 이름은 숨기지 않는다
MIN_SECRET_LENGTH = 2


def keywords_of(entry: EntrySnapshot) -> list[str]:
    """인물의 키워드(장면의 호칭). 빈 것은 뺀다."""
    return [word.strip() for word in entry.keywords if word.strip()]


def hidden_names_of(entry: EntrySnapshot, scene: str) -> set[str]:
    """
    이 인물의 숨길 이름들. 정답으로 적은 이름(true_names)이다.

    키워드, 짧은 이름, 이번 라운드를 연 장면에 이미 나온 이름은 뺀다.
    키워드가 없는 인물은 항목의 이름을 빼지 않으면 부를 이름이 없어서 뺀다.
    """
    keywords = keywords_of(entry)
    names = {name.strip() for name in entry.true_names}
    if not keywords:
        names.discard(entry.name.strip())
    return {name for name in names if len(name) >= MIN_SECRET_LENGTH and name not in keywords and name not in scene}


def public_label(entry: EntrySnapshot, hidden: Set[str], scene: str) -> str:
    """
    이 인물을 대신 부를 호칭. 항목의 이름이 숨길 이름이 아니면 그것이다.

    숨길 이름이면 키워드 중 장면에 나온 가장 긴 것, 나온 것이 없으면 가장 긴 키워드다.
    키워드가 없는 인물은 항목의 이름을 숨기지 않으므로 늘 부를 이름이 있다.
    """
    if entry.name.strip() not in hidden:
        return entry.name
    keywords = keywords_of(entry)
    seen = [word for word in keywords if word in scene]
    return max(seen or keywords, key=len)


def secret_names(entries: Iterable[EntrySnapshot], named: Set, scene: str) -> dict[str, str]:
    """
    아직 맞히지 않은 인물들의 숨길 이름과 대신 부를 호칭.

    entries 는 판의 인물 항목이다. named 는 플레이어가 진짜 이름을 맞힌 인물의 항목 id 다. 그 인물은 숨기지 않는다.
    scene 은 이번 라운드를 연 장면이다. 거기에 이미 나온 이름은 숨기지 않는다.
    """
    secrets: dict[str, str] = {}
    for entry in entries:
        if entry.id in named:
            continue
        hidden = hidden_names_of(entry, scene)
        if hidden:
            secrets.update(dict.fromkeys(hidden, public_label(entry, hidden, scene)))
    return secrets


def leaked(text: str, secrets: SecretNames) -> list[str]:
    """글에 나온 숨길 이름들. 긴 것부터다. 없으면 빈 목록이다."""
    return [name for name in sorted(secrets, key=len, reverse=True) if name in text]


def redact(text: str, secrets: SecretNames) -> str:
    """글의 숨길 이름을 모두 대신 부를 호칭으로 바꾼다. 긴 이름부터 바꾼다(이름이 다른 이름을 품을 때)."""
    return relabel(text, secrets)


def held_length(text: str, secrets: SecretNames) -> int:
    """
    글의 끝에서 잡아 둘 글자 수. 끝이 숨길 이름의 앞부분이면 그 길이, 아니면 0 이다.

    "비올" 로 끝난 조각 뒤에 "레타" 가 오면 "비올레타" 가 된다. 앞부분을 먼저 보내면 가릴 수 없다.
    """
    longest = 0
    for name in secrets:
        for size in range(min(len(name) - 1, len(text)), longest, -1):
            if text.endswith(name[:size]):
                longest = size
                break
    return longest


@dataclass
class GuardedPreview:
    """
    미리 보기를 가려서 넘기는 것. Preview 모양을 따른다. 받은 조각을 모았다가 가린 글만 안쪽으로 넘긴다.

    pending 은 아직 넘기지 않은 글이다. 끝이 숨길 이름의 앞부분일 수 있는 만큼만 남는다.
    시도가 끝날 때 남은 몇 글자는 넘기지 않는다. 서술이 끝나면 다 쓴 장면(gm_narration)이 따로 간다.
    """

    inner: Preview
    secrets: SecretNames
    pending: str = field(default='')

    def begin(self) -> None:
        """새 시도가 시작됐다. 앞의 시도에서 잡아 둔 글은 버린다."""
        self.pending = ''
        self.inner.begin()

    def text(self, piece: str) -> None:
        """조각을 모아, 숨길 이름이 될 수 없는 앞부분을 가려서 넘긴다."""
        self.pending += piece
        cut = len(self.pending) - held_length(self.pending, self.secrets)
        ready = redact(self.pending[:cut], self.secrets)
        self.pending = self.pending[cut:]
        if ready:
            self.inner.text(ready)


def guarded(preview: Preview, secrets: SecretNames) -> Preview:
    """숨길 이름이 있으면 가려서 넘기는 미리 보기, 없으면 그대로다."""
    return GuardedPreview(preview, secrets) if secrets else preview
