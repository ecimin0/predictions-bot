import aiohttp
import discord
from discord.ext import tasks, commands
import urllib
from utils.exceptions import *
from utils.utils import checkBotReady, nextMatch, getPlayerId, checkUserExists
from tabulate import tabulate
from typing import Optional
import os
import utils.models as models

class Utilities(commands.Cog, name="Utility"): # type: ignore
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot
        self.rules_set: str = \
"""**Predict our next match against {0} {1}**

**Prediction League Rules:**
2 points - correct result (W/D/L)
2 points - correct number of Arsenal goals
1 point - correct number of goals conceded
1 point - each correct scorer
1 point - correct FGS (first goal scorer, only Arsenal)
2 points bonus - all scorers correct

- Players you predict to score multiple goals should be entered as `player x2` or `player 2x`
- No points for scorers if your prediction's goals exceed the actual goals by 4+

**Remember, we are only counting Arsenal goal scorers**
    - Do not predict opposition goal scorers
    - Do not predict opposition FGS

**Example:**
`{2}`
"""
    @commands.command()
    async def rules(self, ctx: commands.Context):
        # these 3 quote blocks in all of the commands are returned when user enters +help
        '''
        Display Prediction League Rules
        '''
        predict_example = "+predict 3-0 saka fgs, martinelli, saliba\n(separate using commas)"
        next_match = await nextMatch(self.bot)
        if not next_match:
            next_match = models.Fixture(opponent_name="Party Parrots", fixture_id=999999)

        rules_set_filled = self.rules_set.format(models.Emoji(self.bot, next_match.opponent_name).emoji, next_match.opponent_name, predict_example)
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
    
    # @commands.command(aliases=["bug", "request", "todo"])
    # @commands.cooldown(1, 3600, commands.BucketType.user)
    # async def feedback(self, ctx: commands.Context, *, feedback: Optional[str]):
    #     '''
    #     Open or report an issue on GitLab | +feedback +bug +request +todo
    #     '''
    #     log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)

    #     label = "feedback"
    #     for feedback_type in ["bug", "request", "feedback"]:
    #         if f"+{feedback_type}" in ctx.message.content:
    #             feedback_type = feedback_type
    #             label = f"{feedback_type},{label}"

    #     if not feedback:
    #         await ctx.send("Missing feedback, please ensure you included something.")
    #         ctx.command.reset_cooldown(ctx)
    #     else:
    #         issue_title: str = f"{ctx.author.name}: {feedback}"
    #         async with aiohttp.ClientSession() as session:
    #             async with session.post(f"https://gitlab.com/api/v4/projects/15728299/issues?title={urllib.parse.quote_plus(issue_title)}&description={urllib.parse.quote_plus(feedback)}&labels={label}", headers={'PRIVATE-TOKEN': self.bot.gitlab_api}, timeout=30) as resp:
    #                 fixture_info = await resp.json()
    #         await ctx.send(f"{ctx.message.author.mention}\nThank you for your feedback!")

    @commands.command()
    async def botissues(self, ctx: commands.Context):
        '''
        See list of open bugs, requests, and feedback
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)

        all_issues = []
        output = "**Open Issues:**\n"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://gitlab.com/api/v4/projects/15728299/issues?labels=feedback&state=opened", headers={'PRIVATE-TOKEN': os.environ.get('GITLAB_API', None)}, timeout=30) as resp:
                    issues = await resp.json()
            for issue in issues:
                all_issues.append(issue)

            for issue in all_issues:
                output += f"**{issue.get('references').get('short')}** - `{', '.join(issue.get('labels'))}` | {issue.get('title')}\n"
            await ctx.send(output)
        except Exception:
            log.debug("Error getting issues", all_issues)

    @commands.command()
    async def player(self, ctx: commands.Context, name: str):
        '''
        Search for player by name/letter | +player saka
        '''
        try:
            player_id = await getPlayerId(self.bot, name)
        except Exception as e:
            print("THIS")
            await ctx.send(f"{e}")
        
        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                player_name = await connection.fetchrow("SELECT player_name FROM predictionsbot.players WHERE player_id = $1", player_id)
        
        await ctx.send(f"{player_name.get('player_name')}")


    @commands.command()
    async def check(self, ctx: commands.Context):
        retval = await checkUserExists(self.bot, ctx.message.author.id, ctx.message.author.mention, discord.utils.get(self.bot.emojis, name=self.bot.main_team_name.lower()))
        finalval = await retval.perform(self.bot, ctx)
        # if we ever find that we repeat this pattern in wider use of the monadic stuff, we can write a function to chain async await functions


def setup(bot):
    bot.add_cog(Utilities(bot))
