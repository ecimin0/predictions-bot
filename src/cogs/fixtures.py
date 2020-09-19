import discord
from discord.ext import commands

from utils import getTeamId, formatMatch, nextMatches, getStandings, formatStandings


class FixturesCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def when(self, ctx):
        '''
        Return next match against given team
        '''
        msg = ctx.message.content
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
            await ctx.send(f"{ctx.message.author.mention}\n\n{team} does not seem to be a team I recognize.")
            return

        next_match = await self.bot.pg_conn.fetchrow(f"SELECT {self.bot.match_select} FROM predictionsbot.fixtures f WHERE event_date > now() AND ((home = {self.bot.main_team} AND away = $1) OR (away = {self.bot.main_team} AND home = $1)) ORDER BY event_date LIMIT 1", team_id)
        next_match = await formatMatch(self.bot, next_match, ctx.message.author.id)
        await ctx.send(f"{ctx.message.author.mention}\n\n{next_match}")


    @commands.command()
    async def next(self, ctx):
        '''
        Next matches
        '''
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name)
        msg = ctx.message.content

        split_msg = msg.split()
        
        if len(split_msg) > 2:
            await ctx.send(f"{ctx.message.author.mention}\n\nToo many arguments; should be '+next 2' or similar")
            return

        elif len(split_msg) > 1:
            count = split_msg[1]
            try:
                count = int(count)
            except:
                await ctx.send(f"{ctx.message.author.mention}\n\nExpected usage:\n`+next [1-10]`")
                return
        else: 
            count = 2
            
        if count <= 0:
            await ctx.send(f"{ctx.message.author.mention}\n\nNumber of next matches cannot be a negative number")
        elif count > 10:
            await ctx.send(f"{ctx.message.author.mention}\n\nNumber of next matches cannot be greater than 10")
        else:
            try:
                next_matches = await nextMatches(self.bot, count=count)
            except Exception:
                log.exception("Error retrieving nextMatches from database")
            output = f"{ctx.message.author.mention}\n\n**Next {count} matches:**\n\n"
            for match in next_matches:
            # await ctx.send(f"{[match for match in next_matches]}")
            # todo: embed icons here
                output += await formatMatch(self.bot, match, ctx.message.author.id)
            await ctx.send(f"{output}")

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.default)
    async def pltable(self, ctx):
        '''
        Current Premier League table
        '''
        standings = await getStandings(self.bot, self.bot.league_dict["premier_league"])

        output = formatStandings(standings)
        # \u200b  null space/break char
        # embed = discord.Embed(title=f"Premier League Leaderboard", description=f"```{output}```", color=0x3d195b)
        # embed.set_thumbnail(url="http://www.pngall.com/wp-content/uploads/4/Premier-League-PNG-Image.png")
        # embed.set_footer(text="\u200b", icon_url="https://media.api-sports.io/leagues/2.png")
        # embed.add_field(name="\u200b", value=output, inline=False)
        # embed.add_field(name=f'Rank {makeOrdinal(rank_num)}:  {user_prediction.get("score")} Points', value=f"```{output_str}```", inline=False)
        await ctx.send(f"{ctx.message.author.mention}\n\n**Premier League Leaderboard**\n```{output}```")
        # await ctx.send(f"```{output}```")
        # await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(FixturesCog(bot))