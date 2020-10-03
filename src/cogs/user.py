import discord
from discord.ext import commands
import pytz
import re

from utils.exceptions import *
from utils.utils import getUserTimezone, checkUserExists

class UserCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.command()
    async def timezone(self, ctx):
        '''
        Change timezone
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)
        await checkUserExists(self.bot, ctx.message.author.id, ctx)

        msg: str = ctx.message.content
        try:
            tz = re.search(r"\+timezone (.*)", msg).group(1)
            tz = tz.strip()
        except AttributeError:
            current_tz = await getUserTimezone(self.bot, ctx.message.author.id)
            await ctx.send(f"{ctx.message.author.mention}\nYour current timezone is {current_tz}")
            return
        except Exception:
            await ctx.send(f"{ctx.message.author.mention}\nYou didn't include a timezone!")
            return
        
        if tz in pytz.all_timezones:
            try:
                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute("UPDATE predictionsbot.users SET tz = $1 WHERE user_id = $2", tz, ctx.message.author.id)
            except Exception:
                log.error("User encoutered error changing timezone")
            await ctx.send(f"{ctx.message.author.mention}\nYour timezone has been set to {tz}")
        else:
            await ctx.send(f"{ctx.message.author.mention}\nThat is not a recognized timezone!\nExpected format looks like: 'US/Mountain' or 'America/Chicago' or 'Europe/London'\nSee here for a list of timezones:\nhttps://gist.githubusercontent.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568/raw/daacf0e4496ccc60a36e493f0252b7988bceb143/pytz-time-zones.py")

    @commands.command()
    async def remindme(self, ctx):
        '''
        Toggle prediction reminders on/off
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)
        await checkUserExists(self.bot, ctx.message.author.id, ctx)
        try:
            notify = await self.bot.db.fetchrow("SELECT allow_notifications FROM predictionsbot.users WHERE user_id = $1", ctx.message.author.id)
            # if not notify:
            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("UPDATE predictionsbot.users SET allow_notifications = $1 WHERE user_id = $2", not notify.get("allow_notifications"), ctx.message.author.id)
            await ctx.send(f"{ctx.message.author.mention}\nSending notifications set to **`{not notify.get('allow_notifications')}`**")
        except Exception:
            log.debug("Failed to update notifcation preference")

def setup(bot):
    bot.add_cog(UserCog(bot))