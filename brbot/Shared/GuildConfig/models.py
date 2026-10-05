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
        enable_nsfw: bool,
        animanga_channel: int,
        mtg_channel: int,
        tracked_playgroup_id: int,
    ):
        self.allow_phrases = allow_phrases
        self.limit_user_responses = limit_user_responses
        self.restrict_response_deletion = restrict_response_deletion
        self.max_user_responses = max_user_responses
        self.enable_nsfw = enable_nsfw
        self.animanga_channel = animanga_channel
        self.mtg_channel = mtg_channel
        self.tracked_playgroup_id = tracked_playgroup_id

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
            enable_nsfw=guild_config.enable_nsfw,
            animanga_channel=guild_config.animanga_channel,
            mtg_channel=guild_config.mtg_channel,
            tracked_playgroup_id=guild_config.tracked_playgroup_id,
        )
