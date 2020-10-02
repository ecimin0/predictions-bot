import aiohttp
import discord
from discord.ext import tasks, commands
import urllib
from utils.exceptions import *
from utils.utils import checkBotReady, nextMatch
from tabulate import tabulate

class UtilCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot
        self.rules_set: str = \
"""**Predict our next match against {0}**

**Prediction League Rules:**

2 points – correct result (W/D/L)
2 points – correct number of Arsenal goals
1 point – correct number of goals conceded
1 point – each correct scorer
1 point – correct FGS (first goal scorer, only Arsenal)
2 points bonus – all scorers correct

- Players you predict to score multiple goals should be entered as "player x2" or "player 2x"

- No points for scorers if your prediction's goals exceed the actual goals by 4+

**Remember, we are only counting Arsenal goal scorers**
    - Do not predict opposition goal scorers
    - Do not predict opposition FGS

**Example:**
`{1}`
"""
    @commands.command()
    async def rules(self, ctx: commands.Context):
        # these 3 quote blocks in all of the commands are returned when user enters +help
        '''
        Display Prediction League Rules
        '''
        predict_example = "+predict 3-0 auba 2x fgs, laca"
        next_match = await nextMatch(self.bot)
        opponent = next_match.get('opponent_name')

        rules_set_filled = self.rules_set.format(opponent, predict_example)
        await ctx.send(f"{ctx.message.author.mention}\n{rules_set_filled}")

    @commands.command()
    async def ping(self, ctx: commands.Context):
        '''
        Return latency between bot and server
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)
        latency: float = self.bot.latency
        log.info(latency=latency)
        await ctx.send(f"{ctx.message.author.mention}\nBot latency is {latency * 1000:.0f} milliseconds")

    @commands.command(hidden=True)
    async def echo(self, ctx: commands.Context, *, content:str):
        '''
        Repeat what you typed for testing/debugging
        '''    
        await ctx.send(content)

    # @commands.command(hidden=True)
    # async def what_do_you_think_of_tottenham(self,ctx):
    #     '''
    #     Who do we think is shit?
    #     '''
    #     video = "https://www.youtube.com/watch?v=w0R7gWf-nSA"
    #     spurs_status = "SHIT"
    #     await ctx.send(f"{ctx.message.author.mention}\n{spurs_status}\n{video}")
    
    @commands.command(aliases=["bug"])
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def feedback(self, ctx: commands.Context):
        '''
        Feedback function | leave a short feedback message
        '''
        message: str = ctx.message.content.replace("+feedback ", "")
        message = message.replace("+bug ", "")
        if not message or "+feedback" in message or "+bug" in message:
            await ctx.send("Missing feedback, please ensure you included something.")
            ctx.command.reset_cooldown(ctx)
        else:
            issue_title: str = f"feedback from {ctx.author.name}"
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://gitlab.com/api/v4/projects/15728299/issues?title={urllib.parse.quote_plus(issue_title)}&description={urllib.parse.quote_plus(message)}&labels=feedback", headers={'PRIVATE-TOKEN': self.bot.gitlab_api}, timeout=30) as resp:
                    fixture_info = await resp.json()
            await ctx.send(f"{ctx.message.author.mention}\nThank you for your feedback!")

def setup(bot):
    bot.add_cog(UtilCog(bot))
