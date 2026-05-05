from sqlalchemy.ext.asyncio import AsyncSession
from brbot.Shared.GuildConfig.models import CachedGuildConfig
from brbot.db.models import GuildConfig
from brbot.Core.botdata import default_config
from brbot.Features.Config.data import ConfigKeys
from sqlalchemy import delete, select
import logging

logger = logging.getLogger(__name__)


class ConfigService:
    def __init__(
        self,
        guild_config_cache: dict[int, CachedGuildConfig],
    ):
        self.guild_config_cache = guild_config_cache

    async def set_config(
        self,
        guild_id: int,
        setting_key: ConfigKeys,
        value: bool | int,
        session: AsyncSession,
    ):
        stmt = select(GuildConfig).where(GuildConfig.guild_id == guild_id)

        result = await session.execute(stmt)
        db_guild_config = result.scalar_one_or_none()
        if db_guild_config is None:
            db_guild_config = default_config(guild_id)
            session.add(db_guild_config)

        match setting_key:
            case ConfigKeys.RESTRICT_RESPONSE_DELETION:
                db_guild_config.restrict_response_deletion = bool(value)
            case ConfigKeys.LIMIT_USER_RESPONSES:
                db_guild_config.limit_user_responses = bool(value)
            case ConfigKeys.MAX_USER_RESPONSES:
                db_guild_config.max_user_responses = max(0, min(9999, int(value)))
            case ConfigKeys.ALLOW_PHRASES:
                db_guild_config.allow_phrases = bool(value)
            case ConfigKeys.ENABLE_NSFW:
                db_guild_config.enable_nsfw = bool(value)

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.warning(
                f"Failed to set guild {guild_id} config value {setting_key}: {e}"
            )
            return True

        self.guild_config_cache[guild_id] = CachedGuildConfig.from_guild_config(
            db_guild_config
        )
        return False

    async def wipe_config(self, guild_id: int, session: AsyncSession):
        stmt = delete(GuildConfig).where(GuildConfig.guild_id == guild_id)

        await session.execute(stmt)

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.warning("Failed to wipe guild config", exc_info=e)
            return True

        self.guild_config_cache[guild_id] = CachedGuildConfig.from_guild_config(
            default_config(guild_id)
        )
        return False
