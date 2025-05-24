import interactions
import Features.Help.data as hp
import Core.botdata as bd
import asyncio
import Core.botutils as bu


class Help(interactions.Extension):
    @interactions.slash_command(
        name="help",
        description="View information about the bot's commands.",
        dm_permission=True,
    )
    async def display_help(self, ctx: interactions.SlashContext):
        help_msg = await ctx.send(embed=hp.gen_help_embed(page=0, expired=False), components=hp.help_category_menu)
        sent = bu.ListMsg(
            num=help_msg.id, page=0, guild=ctx.guild, channel=ctx.channel, msg_type="help", payload=None
        )
        bd.active_msgs.append(sent)
        _ = asyncio.create_task(
            bu.close_msg(sent, 300, ctx)
        )