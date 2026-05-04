from dataclasses import dataclass
from brbot.db.models import GuildConfig


@dataclass
class CachedGuildConfig:
    def __init__(
        self,
        allow_phrases: bool,
        limit_user_responses: bool,
        restrict_response_deletion: bool,
        max_user_responses: int,
    ):
        self.allow_phrases = allow_phrases
        self.limit_user_responses = limit_user_responses
        self.restrict_response_deletion = restrict_response_deletion
        self.max_user_responses = max_user_responses

    @classmethod
    def from_guild_config(cls, guild_config: GuildConfig):
        allow_phrases = guild_config.allow_phrases
        limit_user_responses = guild_config.limit_user_responses
        restrict_response_deletion = guild_config.restrict_response_deletion
        max_user_responses = guild_config.max_user_responses
        return cls(
            allow_phrases=allow_phrases,
            limit_user_responses=limit_user_responses,
            restrict_response_deletion=restrict_response_deletion,
            max_user_responses=max_user_responses,
        )
