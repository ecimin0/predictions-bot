import discord
from discord.ext import commands
import pytz
import re

from exceptions import *
from utils import getUserTimezone, checkUserExists

class UserCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def timezone(self, ctx):
        '''
        Change timezone
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)
        await checkUserExists(self.bot, ctx.message.author.id, ctx)

        msg = ctx.message.content
        try:
            tz = re.search(r"\+timezone (.*)", msg).group(1)
        except AttributeError:
            current_tz = await getUserTimezone(self.bot, ctx.message.author.id)
            await ctx.send(f"{ctx.message.author.mention}\n\nYour current timezone is {current_tz}")
            return
        except Exception:
            await ctx.send(f"{ctx.message.author.mention}\n\nYou didn't include a timezone!")
            return
        
        if tz in pytz.all_timezones:
            try:
                async with self.bot.pg_conn.acquire() as connection:
                    async with connection.transaction():
                        await connection.execute("UPDATE predictionsbot.users SET tz = $1 WHERE user_id = $2", tz, ctx.message.author.id)
            except Exception:
                log.error("User encoutered error changing timezone")
            await ctx.send(f"{ctx.message.author.mention}\n\nYour timezone has been set to {tz}")
        else:
            await ctx.send(f"{ctx.message.author.mention}\n\nThat is not a recognized timezone!\nExpected format looks like: 'US/Mountain' or 'America/Chicago' or 'Europe/London'")

def setup(bot):
    bot.add_cog(UserCog(bot))