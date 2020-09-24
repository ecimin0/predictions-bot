import discord
import datetime as dt
from discord.ext import commands
from tabulate import tabulate
from utils.utils import getTeamId, formatMatch, nextMatches, getStandings, formatStandings, checkUserExists, getUserTimezone, prepareTimestamp, completedMatches
from typing import Mapping, List

class FixturesCog(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.command()
    async def when(self, ctx: commands.Context):
        '''
        Return next match against given team | +when <team>
        '''
        msg: str = ctx.message.content
        try:
            team = msg.split(" ", 1)[1]
        except: 
            await ctx.send("Missing a team!")
            return

        try:
            team_id = await getTeamId(self.bot, team)
            if team_id == self.bot.main_team:
                await ctx.send(f"You are on the channel for the {team}, we cannot play against ourselves.")
                return
        except:
            self.bot.logger.exception()
            await ctx.send(f"{ctx.message.author.mention}\n{team} does not seem to be a team I recognize.")
            return

        next_match = await self.bot.db.fetchrow(f"SELECT {self.bot.match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND ((home = {self.bot.main_team} AND away = $1) OR (away = {self.bot.main_team} AND home = $1)) ORDER BY event_date LIMIT 1", team_id)
        next_match = await formatMatch(self.bot, next_match, ctx.message.author.id)
        await ctx.send(f"{ctx.message.author.mention}\n{next_match}")


    @commands.command()
    async def next(self, ctx: commands.Context):
        '''
        Next <number> matches | +next 3
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)
        msg: str = ctx.message.content

        split_msg = msg.split()
        
        if len(split_msg) > 2:
            await ctx.send(f"{ctx.message.author.mention}\nToo many arguments; should be '+next 2' or similar")
            return

        elif len(split_msg) > 1:
            count_str = split_msg[1]
            try:
                count: int = int(count_str)
            except:
                await ctx.send(f"{ctx.message.author.mention}\nExpected usage:\n`+next [1-10]`")
                return
        else: 
            count = 2
            
        if count <= 0:
            await ctx.send(f"{ctx.message.author.mention}\nNumber of next matches cannot be a negative number")
        elif count > 30:
            await ctx.send(f"{ctx.message.author.mention}\nNumber of next matches cannot be greater than 10")
        else:
            try:
                next_matches = await nextMatches(self.bot, count=count)
            except Exception:
                log.exception("Error retrieving nextMatches from database")
            output = f"{ctx.message.author.mention}\n**Next {count} matches:**\n\n"
            for match in next_matches:
                output += await formatMatch(self.bot, match, ctx.message.author.id)
            await ctx.send(f"{output}")

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.default)
    async def pltable(self, ctx: commands.Context):
        '''
        Current Premier League table
        '''
        standings: List[Mapping] = await getStandings(self.bot, self.bot.league_dict["premier_league"])

        output = formatStandings(standings)
        # \u200b  null space/break char
        # embed = discord.Embed(title=f"Premier League Leaderboard", description=f"```{output}```", color=0x3d195b)
        # embed.set_thumbnail(url="http://www.pngall.com/wp-content/uploads/4/Premier-League-PNG-Image.png")
        # embed.set_footer(text="\u200b", icon_url="https://media.api-sports.io/leagues/2.png")
        # embed.add_field(name="\u200b", value=output, inline=False)
        # embed.add_field(name=f'Rank {makeOrdinal(rank_num)}:  {user_prediction.get("score")} Points', value=f"```{output_str}```", inline=False)
        await ctx.send(f"{ctx.message.author.mention}\n\n**<:premierleague:756634419837665361> Premier League Leaderboard <:premierleague:756634419837665361>**\n```{output}```")
        # await ctx.send(f"```{output}```")
        # await ctx.send(embed=embed)

    @commands.command()
    async def results(self, ctx: commands.Context):
        '''
        Return historical match results
        '''
        await checkUserExists(self.bot, ctx.message.author.id, ctx)
        user_tz: dt.tzinfo = await getUserTimezone(self.bot, ctx.message.author.id)

        done_matches = await completedMatches(self.bot, count=10)
        done_matches_output = []
        for match in done_matches:
        #     match_time = match.get("event_date")
        #     match_time = prepareTimestamp(match_time, user_tz, str=False)
        #     done_matches_output.append([match_time.strftime("%m/%d/%Y"), match.get("home_name"), f'{match.get("goals_home")}-{match.get("goals_away")}', match.get("away_name")])

        # done_matches_output = f'```{tabulate(done_matches_output, headers=["Date", "Home", "Score", "Away"], tablefmt="github", colalign=("center","center","center","center"))}```'
            done_matches_output.append(await formatMatch(self.bot, match, ctx.message.author.id, score=True))
        
        done_matches_output_str = "\n".join(done_matches_output)
        await ctx.send(f"{ctx.message.author.mention}\n**Past Match Results**\n\n{done_matches_output_str}")

def setup(bot):
    bot.add_cog(FixturesCog(bot))