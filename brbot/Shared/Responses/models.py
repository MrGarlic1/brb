from dataclasses import dataclass
from emoji import emojize


@dataclass
class CachedResponse:
    def __init__(self, trigger: str, text: str, behavior: int, member_id: int):
        self.trigger = emojize(trigger)
        self.text = emojize(text)
        self.behavior = behavior
        self.member_id = member_id
        self.trigger_lower = self.trigger.lower()

    def __eq__(self, other):
        return (
            self.trigger == other.trigger
            and self.text == other.text
            and self.behavior == other.behavior
        )
