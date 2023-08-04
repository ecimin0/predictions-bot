import sys
import discord
import datetime as dt
import aiohttp
import utils.models as models
from discord.ext import commands
from tabulate import tabulate
from utils.exceptions import *
from utils.utils import getTeamId, formatMatch, nextMatch, nextMatches, getStandings, formatStandings, checkUserExists, getUserTimezone, prepareTimestamp, completedMatches, makePaged, getApiPrediction
from typing import Mapping, List, Union, Optional

class Fixtures(commands.Cog, name="Fixtures"): # type: ignore

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.command(aliases=["fixtures", "when"])
    async def next(self, ctx: commands.Context, *, msg: Optional[Union[int, str]]):
        '''
        Upcoming matches or next match against another side | [+next 3 | +next wolves]
        '''
        await checkUserExists(self.bot, ctx.message.author.id, ctx)
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)

        if type(msg) == int or not msg:
            output_array = []

            if not msg:
                count = 2
            else:
                count = int(msg)
                
            if count <= 0:
                await ctx.send(f"{ctx.message.author.mention}\nNumber of next matches cannot be a negative number")
            elif count >= 20:
                await ctx.send(f"{ctx.message.author.mention}\nNumber of next matches cannot be greater than 20")
            else:
                try:
                    next_matches = await nextMatches(self.bot, count=count)
                except Exception:
                    log.exception("Error retrieving nextMatches from database")
                output = f"{ctx.message.author.mention}\n**Next {count} matches:**\n"

                addV3P = False
                for match in next_matches:
                    if addV3P:
                        output_array.append(await formatMatch(self.bot, match, ctx.message.author.id))
                        output_array.append(f"\n*Click to view API Prediction:*\n{await getApiPrediction(self.bot, match)}\n\n")
                        addV3P = False
                    else:
                        output_array.append(f"{await formatMatch(self.bot, match, ctx.message.author.id)}\n\n")

                paged_results = []
                for i in range(0, len(output_array), self.bot.step):
                    paged_results.append(output + ''.join(output_array[i:i+self.bot.step]))

                if not paged_results:
                    await ctx.send(f"{ctx.message.author.mention}\nNo upcoming matches found.")
                else:
                    await makePaged(self.bot, ctx, paged_results)
        elif type(msg) == str:
            team = str(msg)

            try:
                team_id = await getTeamId(self.bot, team)
                if team_id == self.bot.main_team:
                    await ctx.send(f"You are on the channel for {team.capitalize()}, we cannot play against ourselves.")
                    return
            except TooManyResults as e:
                log.exception()
                await ctx.send(f"{ctx.message.author.mention}\n{e}")
                return
            except Exception:
                log.exception()
                await ctx.send(f"{ctx.message.author.mention}\n{team} does not seem to be a team I recognize.")
                return

            try:
                next_match = await nextMatch(self.bot, team_id)
                if not next_match:
                    await ctx.send(f"{ctx.message.author.mention}\n{self.bot.main_team_name} does not have any upcoming matches against {team}.")
                else:
                    fmt_match = await formatMatch(self.bot, next_match, ctx.message.author.id)
                    prediction = await getApiPrediction(self.bot, next_match)
                    await ctx.send(f"{ctx.message.author.mention}\n{fmt_match}\n*API Prediction:*\n{prediction}")
            except TypeError as e:
                await ctx.send(f"sorry, something went wrong")
                log.error(e)


    @commands.command(aliases=["table", "standings"])
    @commands.cooldown(1, 60, commands.BucketType.default)
    async def pltable(self, ctx: commands.Context):
        '''
        Current Premier League table | Once every 60s
        '''
        standings: List[Mapping] = await getStandings(self.bot, self.bot.v3league_dict["v3premier_league"])

        output = formatStandings(standings)
        # \u200b  null space/break char
        await ctx.send(f"{ctx.message.author.mention}\n\n**<:premierleague:756634419837665361> Premier League Leaderboard <:premierleague:756634419837665361>**\n```{output}```")


    @commands.command(aliases=["past"])
    @commands.command()
    async def results(self, ctx: commands.Context):
        '''
        Return past fixture results
        '''
        await checkUserExists(self.bot, ctx.message.author.id, ctx)
        user_tz: dt.tzinfo = await getUserTimezone(self.bot, ctx.message.author.id)

        done_matches = await completedMatches(self.bot, count=10)
        done_matches_output = []
        for match in done_matches:
            done_matches_output.append(await formatMatch(self.bot, match, ctx.message.author.id, score=True))
        
        paged_results = []
        for i in range(0, len(done_matches_output), self.bot.step):
            paged_results.append(f"{ctx.message.author.mention}\n**Past Match Results**\n\n" + '\n'.join(done_matches_output[i:i+self.bot.step]))

        await makePaged(self.bot, ctx, paged_results)

def setup(bot):
    bot.add_cog(Fixtures(bot))