from dataclasses import dataclass
from emoji import emojize


@dataclass
class CachedResponse:
    def __init__(self, trigger: str, text: str, exact: bool, member_id: int):
        self.trigger = emojize(trigger)
        self.text = emojize(text)
        self.exact = exact
        self.member_id = member_id

    def __eq__(self, other):
        return (
            self.trigger == other.trigger
            and self.text == other.text
            and self.exact == other.exact
        )
