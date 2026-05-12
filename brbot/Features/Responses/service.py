from emoji import demojize
import brbot.Core.botdata as bd
from brbot.Features.Responses.data import ResponseType
from brbot.db.models import Response, Member
from brbot.Shared.Responses.models import CachedResponse
from brbot.Shared.GuildConfig.models import CachedGuildConfig
import logging
from discord import Guild, Embed, Message
from random import choice
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, func
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


class ResponseService:
    def __init__(
        self,
        exact_cache: dict[int, dict[str, list[CachedResponse]]],
        phrase_cache: dict[int, list[CachedResponse]],
        correction_cache: dict[int, list[CachedResponse]],
        guild_config_cache: dict[int, CachedGuildConfig],
    ):
        self.exact_responses = exact_cache
        self.phrase_responses = phrase_cache
        self.correction_responses = correction_cache
        self.guild_configs = guild_config_cache

    # Load response caches on bot setup.
    async def load_responses(self, session: AsyncSession):
        stmt = select(Response)
        result = await session.execute(stmt)
        response_list: Sequence[Response] = result.scalars().all()
        guild_ids = {response.guild_id for response in response_list}

        for guild_id in guild_ids:
            self.exact_responses[guild_id] = {}
            self.phrase_responses[guild_id] = []
            self.correction_responses[guild_id] = []

        for response in response_list:
            behavior: int = response.behavior
            if behavior == ResponseType.Exact:
                self.exact_responses[response.guild_id].setdefault(
                    response.trigger, []
                ).append(
                    CachedResponse(
                        trigger=response.trigger,
                        text=response.text,
                        behavior=response.behavior,
                        member_id=response.member_id,
                    )
                )
            elif behavior == ResponseType.Phrase:
                self.phrase_responses[response.guild_id].append(
                    CachedResponse(
                        trigger=response.trigger,
                        text=response.text,
                        behavior=response.behavior,
                        member_id=response.member_id,
                    )
                )
            else:
                self.correction_responses[response.guild_id].append(
                    CachedResponse(
                        trigger=response.trigger,
                        text=response.text,
                        behavior=response.behavior,
                        member_id=response.member_id,
                    )
                )

        logger.info(f"Loaded {len(response_list)} responses")

    async def add_response(
        self, guild_id: int, rsp: CachedResponse, session: AsyncSession
    ) -> bool:
        rsp_to_add = Response(
            guild_id=guild_id,
            member_id=rsp.member_id,
            trigger=demojize(rsp.trigger),
            text=demojize(rsp.text),
            behavior=rsp.behavior,
        )

        session.add(rsp_to_add)
        try:
            await session.commit()

            # Add to memory cache
            if rsp.behavior == ResponseType.Exact.value:
                if rsp.trigger in self.exact_responses[guild_id]:
                    self.exact_responses[guild_id][rsp.trigger].append(rsp)
                else:
                    self.exact_responses[guild_id][rsp.trigger] = [rsp]
            elif rsp.behavior == ResponseType.Phrase.value:
                self.phrase_responses[guild_id].append(rsp)
            else:
                self.correction_responses[guild_id].append(rsp)

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
            .where(Response.behavior == delete_req.behavior)
        )

        try:
            # Remove persistent from DB
            await session.execute(stmt)
            await session.commit()

            # Remove from memory cache
            if delete_req.behavior == ResponseType.Exact.value:
                self.exact_responses[guild_id][delete_req.trigger].remove(delete_req)
            elif delete_req.behavior == ResponseType.Phrase.value:
                self.phrase_responses[guild_id].remove(delete_req)
            else:
                self.correction_responses[guild_id].remove(delete_req)

        except Exception as e:
            logger.warning(f"Could not remove response from guild {guild_id}: {e}")
            await session.rollback()
            return True

        return False

    async def get_response_add_validation_error(
        self, guild_id: int, member: Member, behavior: int, session: AsyncSession
    ) -> Optional[str]:
        guild_config = self.guild_configs[guild_id]

        if not guild_config.allow_phrases and behavior in (
            ResponseType.Phrase,
            ResponseType.Correction,
        ):
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
        self.exact_responses[guild_id] = {}
        self.phrase_responses[guild_id] = []

    def get_resp(
        self, guild_id: int, trig: str, text: str = "", behavior: int = None
    ) -> CachedResponse | None:
        responses = [
            rsp
            for rsp_group in self.exact_responses[guild_id].values()
            for rsp in rsp_group
        ] + self.phrase_responses[guild_id]
        fetched_response: Optional[CachedResponse] = None
        matches = 0
        for rsp in responses:
            if rsp.trigger == trig:
                if rsp.text == text or not text:
                    if rsp.behavior == behavior or behavior is None:
                        matches += 1
                        fetched_response = rsp
        if matches != 1:
            return None

        return fetched_response

    def gen_resp_list(self, guild: Guild, page: int) -> Embed:
        guild_id = int(guild.id)
        list_msg = Embed(description="*Your response list, sir.*")

        # Determine max pg @ 10 entries per pg
        responses = [
            rsp
            for rsp_group in self.exact_responses[guild_id].values()
            for rsp in rsp_group
        ] + self.phrase_responses[guild_id]

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
            pref: str = f"**{ResponseType(responses[i].behavior).name}:** "
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
        matches = self.exact_responses[message.guild.id].get(content)
        if matches:
            to_send = [rsp.text for rsp in matches]

            logger.debug(
                f"Exact response match found, 1/{len(to_send)} possible responses"
            )
            return choice(to_send)

        if not self.guild_configs[message.guild.id].allow_phrases:
            return None

        to_send = [
            response.text
            for response in self.phrase_responses[message.guild.id]
            if response.trigger in content
        ]
        logger.debug(
            f"Phrase response match found, 1/{len(to_send)} possible responses"
        )
        if to_send:
            return choice(to_send)

        to_send = []

        for rsp in self.correction_responses[message.guild.id]:
            trigger_lower = rsp.trigger_lower
            idx = content.find(trigger_lower)
            if idx != -1:
                to_send.append((idx, rsp))

        if to_send:
            idx, rsp = choice(to_send)
            return (
                message.content[:idx]
                + rsp.text
                + message.content[idx + len(rsp.trigger) :]
                + "*"
            )

        return None
