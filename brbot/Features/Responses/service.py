from emoji import demojize
import json
import brbot.Core.botdata as bd
from brbot.db.models import Response, Member
from brbot.Shared.Responses.models import CachedResponse
from brbot.Shared.GuildConfig.models import CachedGuildConfig
from brbot.Shared.Members.repository import get_or_create_member
from pathlib import Path
import logging
from discord import Guild, Embed, Message
from random import choice
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy import delete, select, func
from typing import Optional

logger = logging.getLogger(__name__)


class ResponseService:
    def __init__(
        self,
        exact_cache: dict[int, list[CachedResponse]],
        phrase_cache: dict[int, list[CachedResponse]],
        guild_config_cache: dict[int, CachedGuildConfig],
    ):
        self.exact_responses = exact_cache
        self.phrase_responses = phrase_cache
        self.guild_configs = guild_config_cache

    async def add_response(
        self, guild_id: int, rsp: CachedResponse, session: AsyncSession
    ) -> bool:
        rsp_to_add = Response(
            guild_id=guild_id,
            member_id=rsp.member_id,
            trigger=demojize(rsp.trigger),
            text=demojize(rsp.text),
            is_exact=rsp.exact,
        )

        session.add(rsp_to_add)
        try:
            await session.commit()

            # Add to memory cache
            if rsp.exact:
                self.exact_responses[guild_id].append(rsp)
            else:
                self.phrase_responses[guild_id].append(rsp)

        except Exception as e:
            logger.warning(f"Could not add response to guild {guild_id}: {e}")
            await session.rollback()
            return True

        return False

    async def remove_response(
        self, guild_id: int, delete_req: CachedResponse, session: AsyncSession
    ) -> bool:
        stmt = (
            delete(Response)
            .where(Response.guild_id == guild_id)
            .where(Response.trigger == demojize(delete_req.trigger))
            .where(Response.text == demojize(delete_req.text))
        )

        try:
            # Remove persistent from DB
            await session.execute(stmt)
            await session.commit()

            # Remove from memory cache
            if delete_req.exact:
                self.exact_responses[guild_id].remove(delete_req)
            else:
                self.phrase_responses[guild_id].remove(delete_req)

        except Exception as e:
            logger.warning(f"Could not remove response from guild {guild_id}: {e}")
            await session.rollback()
            return True

        return False

    async def get_response_add_validation_error(
        self, guild_id: int, member: Member, exact: bool, session: AsyncSession
    ) -> Optional[str]:
        guild_config = self.guild_configs[guild_id]

        if not guild_config.allow_phrases and not exact:
            return "The server does not allow for phrase-based responses."

        if guild_config.limit_user_responses:
            member_response_count = await ResponseService.get_member_response_count(
                member, session
            )
            if member_response_count >= guild_config.max_user_responses:
                return (
                    f"You currently have the server maximum of {guild_config.max_user_responses} "
                    f"responses and are unable to add more!"
                )

        return None

    async def get_response_remove_validation_error(
        self, guild_id: int, member: Member, response: CachedResponse
    ) -> Optional[str]:
        guild_config = self.guild_configs[guild_id]

        if guild_config.restrict_response_deletion and response.member_id != member.id:
            return "The server settings do not allow you to delete other people's responses."

        return None

    @staticmethod
    async def get_member_response_count(member, session: AsyncSession) -> int:
        stmt = (
            select(func.count())
            .select_from(Response)
            .where(Response.member_id == member.id)
        )
        total = await session.scalar(stmt)
        return total

    @staticmethod
    async def migrate_responses(
        data_dir: Path, session_generator: async_sessionmaker
    ) -> None:
        """
        Temporary function ran once to migrate responses from old file/json schema to DB.
        Args:
            data_dir: file path
            session_generator: async session generator

        Returns:

        """
        responses_to_add: list[Response] = []
        for x in data_dir.iterdir():
            guild_id = int(x.name)
            if x.is_file():
                continue
            try:
                with open(x / "responses.json", "r") as f:
                    try:
                        file_responses: list[dict] = json.load(f)
                    except ValueError:
                        file_responses: list[dict] = []
            except FileNotFoundError:
                return

            for idx, rsp in enumerate(file_responses):
                async with session_generator() as session:
                    member: Member = await get_or_create_member(
                        rsp["user_id"], guild_id, session
                    )
                    member_id = member.id
                if any(
                    r.guild_id == guild_id
                    and r.trigger == demojize(rsp["trig"].lower())
                    and r.text == demojize(rsp["text"])
                    and r.is_exact == rsp["exact"]
                    for r in responses_to_add
                ):
                    logger.info("SKIPPING DUPLICATE")
                    continue
                responses_to_add.append(
                    Response(
                        guild_id=guild_id,
                        member_id=member_id,
                        trigger=demojize(rsp["trig"].lower()),
                        text=demojize(rsp["text"]),
                        is_exact=rsp["exact"],
                    )
                )
                logger.info(
                    f"Staged {len(responses_to_add)} responses for migration in guild {guild_id}"
                )

        async with session_generator() as session:
            session.add_all(responses_to_add)
            await session.commit()

        logger.info(
            f"Successfully migrated {len(responses_to_add)} responses in total."
        )
        return

    async def remove_all_guild_responses(
        self, guild_id: int, session: AsyncSession
    ) -> None:
        stmt = delete(Response).where(Response.guild_id == guild_id)
        try:
            await session.execute(stmt)
            await session.commit()
        except Exception as e:
            logger.warning(f"Could not remove all responses from guild {guild_id}: {e}")
            return

        # Clear memory cache
        self.exact_responses[guild_id] = []
        self.phrase_responses[guild_id] = []

    def get_resp(
        self, guild_id: int, trig: str, text: str = "", exact: bool = None
    ) -> CachedResponse | None:
        responses = self.exact_responses[guild_id] + self.phrase_responses[guild_id]
        fetched_response: Optional[CachedResponse] = None
        matches = 0
        for rsp in responses:
            if rsp.trigger == trig:
                if rsp.text == text or not text:
                    if rsp.exact == exact or exact is None:
                        matches += 1
                        fetched_response = rsp
        if matches != 1:
            return None

        return fetched_response

    def gen_resp_list(self, guild: Guild, page: int) -> Embed:
        guild_id = int(guild.id)
        list_msg = Embed(description="*Your response list, sir.*")

        # Determine max pg @ 10 entries per pg
        responses = self.exact_responses[guild_id] + self.phrase_responses[guild_id]

        max_pages: int = 1 if len(responses) <= 10 else len(responses) // 10 + 1
        page: int = 1 + ((page - 1) % max_pages)  # Loop back through pages both ways
        list_msg.set_author(name=guild.name, icon_url=bd.bot_avatar_url)
        list_msg.set_thumbnail(url=guild.icon.url)
        list_msg.set_footer(text=f"Page {page}/{max_pages}")
        nums: range = (
            range((page - 1) * 10, len(responses))
            if page == max_pages
            else range((page - 1) * 10, page * 10)
        )

        for i in nums:
            pref: str = (
                "**Exact Trigger:** " if responses[i].exact else "**Phrase Trigger:** "
            )
            rsp_field: str = (
                f"{pref}{responses[i].trigger} \n **Respond: ** {responses[i].text}"
            )
            if len(rsp_field) >= 1024:
                logger.debug(
                    f"Response too long: {rsp_field}, showing shortened version"
                )
                rsp_field: str = (
                    f"{pref}{responses[i].trigger} \n "
                    f"**Respond: ** *[Really, really, really long response]*"
                )

            list_msg.add_field(name="\u200b", value=rsp_field, inline=False)
        return list_msg

    def generate_response(
        self,
        message: Message,
    ) -> str | None:
        if message.author.bot:
            return None
        channel = message.channel
        if channel.type == 1:  # Ignore DMs
            return None

        content = message.content.lower()
        to_send = [
            response.text
            for response in self.exact_responses[message.guild.id]
            if response.trigger == content and response.exact
        ]
        logger.debug(f"Exact response match found, 1/{len(to_send)} possible responses")
        if to_send:
            return choice(to_send)

        if not self.guild_configs[message.guild.id].allow_phrases:
            return None

        to_send = [
            response.text
            for response in self.phrase_responses[message.guild.id]
            if response.trigger in content and not response.exact
        ]
        logger.debug(
            f"Phrase response match found, 1/{len(to_send)} possible responses"
        )
        if to_send:
            return choice(to_send)

        return None
