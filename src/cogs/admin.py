import asyncpg
import aiohttp
import discord
from discord.ext import commands
from tabulate import tabulate
from typing import Union
from utils.exceptions import *
from utils.utils import formatMatch, isAdmin, getPlayerId, nextMatch, checkUserExists, nextMatches, getApiPrediction, makePaged, makePagedEmbed
from typing import Mapping, List, Union, Optional
import utils.models as models

class AdminCog(commands.Cog, command_attrs=dict(hidden=True)): # type: ignore

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    async def cog_check(self, ctx: commands.Context):
        if ctx.message.author.id in self.bot.admin_ids:
            return True
        else:
            raise IsNotAdmin(f"User {ctx.message.author.name} is not an admin and cannot use this function.")

    @commands.command()
    async def show_guild_id(self, ctx: commands.Context):
        await ctx.send(f"{ctx.guild.id}") 

    @commands.command(name='list_cogs')
    async def list_cogs(self, ctx: commands.Context):
        output = ""
        for cog in self.bot.cogs:
            output += f"{cog}\n"
        await ctx.send(output) 
        
    @commands.command(name='load')
    async def load(self, ctx: commands.Context, *, cog: str):
        """Command which loads a Module.
        Remember to use dot path. e.g: cogs.owner"""

        try:
            self.bot.load_extension(cog)
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('**`SUCCESS`**')

    @commands.command(name='unload')
    async def unload(self, ctx: commands.Context, *, cog: str):
        """Command which Unloads a Module.
        Remember to use dot path. e.g: cogs.owner"""

        try:
            self.bot.unload_extension(cog)
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('**`SUCCESS`**')

    @commands.command()
    async def userLookup(self, ctx: commands.Context, *input_str:str):
        '''
        Return possible user matches and user ID | +userLookup <partial name>
        '''
        for input in input_str:
            if len(input) < 5:
                await ctx.send(f"Search string must be at least 5 characters long, you entered `{input}`")
                continue

            current_member = []
            for member in self.bot.get_all_members():
                if input.lower() in member.display_name.lower() or input.lower() in member.name.lower():
                    current_member.append(member)
            if not current_member:
                await ctx.send(f"Could not find any users matching {input}.")
            else:
                output = f"Potential Matches for {input}:\n"
                for user in current_member:
                    output += f"{user.display_name} | {user.id}\n"
                await ctx.send(f"{output}")

    @commands.command()
    async def messageLookup(self, ctx: commands.Context, input_id: int):
        '''
        Return message ID and ID of message author | +messageLookup <message ID>
        '''
        id_to_lookup = input_id
        output: Union[discord.Message, None] = None
        for chan in self.bot.get_all_channels():
            if str(chan.type) == "text":
                self.bot.logger.debug(f"Searching channel: {chan}")
                try:
                    output = await chan.fetch_message(id_to_lookup)
                except (discord.NotFound):
                    continue
                except discord.Forbidden:
                    self.bot.logger.debug(f"Access to {chan} forbidden.")
        if not output:
            self.bot.logger.debug("Could not find in any channels.")
            await ctx.send(f"Could not find message id {id_to_lookup}.")
        else:
            await ctx.send(f"Message id {id_to_lookup} | Author: {output.author.id}")

    @commands.command()
    async def addNickname(self, ctx: commands.Context, nicknameType:str, id:int, nickname: str):
        '''
        Add a nickname to database | +addNickname (player|team) <id> <nickname string>
        '''
        try:
            if nicknameType == "team":
                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        updated_count = await connection.execute("UPDATE predictionsbot.teams SET nicknames = array_append(nicknames, $1) WHERE team_id = $2", nickname.lower(), id)
                        await ctx.send(f"Added nickname: `{nickname}` for team id {id} status: `{updated_count}`")
            elif nicknameType == "player":
                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        updated_count = await connection.execute("UPDATE predictionsbot.players SET nicknames = array_append(nicknames, $1) WHERE player_id = $2", nickname.lower(), id)
                        await ctx.send(f"Added nickname: `{nickname}` for player id {id} status: `{updated_count}`")
            else:
                await ctx.send("Can only update nicknames for `player` and `team`.")
        except asyncpg.DataError as e:
            await ctx.send(f"Unable to add nickname: `{nickname}` for id {id} status: `{e}`")

    @commands.command()
    async def removeNickname(self, ctx: commands.Context, nicknameType:str, id:int, nickname:str):
        '''
        Remove a nickname from database | +removeNickname (player|team) <id> <nickname string>
        '''
        try:
            if nicknameType == "team":
                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        updated_count = await connection.execute("UPDATE predictionsbot.teams SET nicknames = array_remove(nicknames, $1) WHERE team_id = $2", nickname, id)
                        await ctx.send(f"Removed nickname: `{nickname}` for team id {id} status: `{updated_count}`")
            elif nicknameType == "player":
                async with self.bot.db.acquire() as connection:
                    async with connection.transaction():
                        updated_count = await connection.execute("UPDATE predictionsbot.players SET nicknames = array_remove(nicknames, $1) WHERE player_id = $2", nickname, id)
                        await ctx.send(f"Removed nickname: `{nickname}` for player id {id} status: `{updated_count}`")
            else:
                await ctx.send("Can only update nicknames for `player` and `team`.")
        except asyncpg.DataError as e:
            await ctx.send(f"Unable to add nickname: `{nickname}` for id {id} status: `{e}`")

    @commands.command(aliases=["players"])
    @commands.cooldown(1, 60, commands.BucketType.default)
    async def listPlayers(self, ctx: commands.Context):
        '''
        ID, name, nicknames for players | Once per 60s
        '''
        ids = await self.bot.db.fetch("SELECT player_id, player_name, nicknames FROM predictionsbot.players WHERE team_id = $1 and active = true", self.bot.main_team)
        playerspaged = []
        player_list = [models.Player(**p) for p in ids]
        players = [f"{p.player_id}, {p.player_name}, {p.nicknames}" for p in player_list]
        players.sort()
        for i in range(0, len(players) + 1, self.bot.step):
            playerspaged.append('\n'.join(players[i:i+self.bot.step]))
        await ctx.send(f"{ctx.message.author.mention}")
        await makePaged(self.bot, ctx, playerspaged)

    @commands.command()
    async def disable(self, ctx: commands.Context, command_name: str):
        '''
        Disables a function/command | +disable <function name>
        '''
        if command_name in self.bot.all_commands:
            command = self.bot.all_commands.get(command_name)
            command.enabled = False
            await ctx.send(f"disabled function {command_name}")
            return

    @commands.command()
    async def enable(self, ctx: commands.Context, command_name: str):
        '''
        Enables a function/command | +disable <function name>
        '''
        if command_name in self.bot.all_commands:
            command = self.bot.all_commands.get(command_name)
            command.enabled = True
            await ctx.send(f"enabled function {command_name}")
            return

    @commands.command(aliases=["toggle"])
    async def togglePlayer(self, ctx: commands.Context, player_name: str):
        '''
        Toggle ability to select player using +predict or +player | +togglePlayer <henry>
        '''
        try:
            player_id = await getPlayerId(self.bot, player_name, active_only=False)
            rawplayer = await self.bot.db.fetchrow("SELECT player_id, player_name, active FROM predictionsbot.players WHERE player_id = $1;", player_id)
            player = models.Player(**rawplayer)

            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("UPDATE predictionsbot.players SET active = $1 WHERE player_id = $2", not player.active, player.player_id)
                    await ctx.send(f"Toggled {player.player_name} to active: {not player.active}")
        except Exception as e:
            await ctx.send(f"{ctx.message.author.mention}\nPlease try again, {e}")


    @commands.command(brief="match prediction from v3 API", aliases=["v3prediction"])
    async def v3p(self, ctx: commands.Context, *, msg: Optional[Union[int, str]]):
        '''
        Show API v3 prediction for next fixture
        '''
        retval = await checkUserExists(self.bot, ctx.message.author.id, ctx.message.author.mention, discord.utils.get(self.bot.emojis, name=self.bot.main_team_name.lower()))
        finalval = await retval.perform(self.bot, ctx)

        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name, command="v3p")
        next_match = await nextMatch(self.bot)
        fmt_match = await formatMatch(self.bot, next_match, ctx.message.author.id)
        prediction = await getApiPrediction(self.bot, next_match)
        await ctx.send(f"{ctx.message.author.mention}\n{fmt_match}\n*API Prediction:*\n{prediction}")

def setup(bot):
    bot.add_cog(AdminCog(bot))