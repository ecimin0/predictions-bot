import asyncpg
import aiohttp
import discord
from discord.ext import commands
from tabulate import tabulate
from typing import Union
from utils.exceptions import *
from utils.utils import isAdmin, getPlayerId, nextMatch, checkUserExists
from typing import Mapping, List, Union, Optional

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
        """Command which Loads a Module.
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
        Return possible user matches and user ID
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
        Return message ID and ID of message author
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

    @commands.command()
    async def listPlayers(self, ctx: commands.Context):
        '''
        list nicknames in database
        '''
        # if nicknameType == "team":
            # pass
            # async with bot.db.acquire() as connection:
            #     async with connection.transaction():
            #         await connection.execute("UPDATE predictionsbot.teams SET nicknames = array_remove(nicknames, $1) WHERE team_id = $2", nickname, id)
        # elif nicknameType == "player":
        if True:
            ids = await self.bot.db.fetch("SELECT player_id, player_name, nicknames FROM predictionsbot.players WHERE team_id = $1", self.bot.main_team)
            output = []
            for player in ids:
                output.append([player.get("player_id"), player.get("player_name")])
            # print(output)
            await ctx.send(f"{ctx.message.author.mention}\n{tabulate(output)}")
        else:
            await ctx.send(f"{ctx.message.author.mention}\nCan only view nicknames/id for `player` and `team`.")

    @commands.command()
    async def disable(self, ctx: commands.Context, command_name: str):
        '''
        Disables a function/command | +disable <function name>
        '''
        if command_name in self.bot.all_commands:
            command = self.bot.all_commands.get(command_name)
            print(f"{command} {command.name}")
            command.update(enabled=False)
            await ctx.send(f"Disabled your shit. {command_name}")
            return

    @commands.command()
    async def enable(self, ctx: commands.Context, command_name: str):
        '''
        Enables a function/command | +disable <function name>
        '''
        if command_name in self.bot.all_commands:
            command = self.bot.all_commands.get(command_name)
            print(f"{command} {command.name}")
            command.update(enabled=True)
            await ctx.send(f"Enabled your shit. {command_name}")
            return

    @commands.command()
    async def togglePlayer(self, ctx: commands.Context, player_name: str):
        '''
        Toggle ability to select player using +predict or +player | +togglePlayer <henry>
        '''
        try:
            player_id = await getPlayerId(self.bot, player_name, active_only=False)
            player = await self.bot.db.fetchrow("SELECT player_name, active FROM predictionsbot.players WHERE player_id = $1;", player_id)
            real_name = player.get("player_name")
            active = player.get("active")

            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    updated_player = await connection.execute("UPDATE predictionsbot.players SET active = $1 WHERE player_id = $2", not active, player_id)
                    await ctx.send(f"Toggled {real_name} to active: {not active}")
        except Exception as e:
            await ctx.send(f"{ctx.message.author.mention}\nPlease try again, {e}")

    @commands.command(brief="match prediction from v3 API", aliases=["v3prediction"])
    async def v3p(self, ctx: commands.Context, *, msg: Optional[Union[int, str]]):
        '''
        Show API v3 prediction for next fixture
        '''
        await checkUserExists(self.bot, ctx.message.author.id, ctx)
        log = self.bot.logger.bind(content=ctx.message.content, author=ctx.message.author.name, command="v3p")
        next_match = await nextMatch(self.bot)
        next_match_id = next_match.get("fixture_id")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://v3.football.api-sports.io/predictions?fixture={next_match_id}", headers={'X-RapidAPI-Key': self.bot.api_key}, timeout=60) as resp:
                    response = await resp.json()
        except Exception as e:
            log.info("e")
            await ctx.send(f"{ctx.message.author.mention}\nFailed to get v3 API prediction\n{e}")

        v3predictions = response.get("response")[0]
        v3pwinner = v3predictions.get('predictions').get('winner').get('name')
        v3pcomment = v3predictions.get('predictions').get('winner').get('comment')
        v3ppercents = v3predictions.get('predictions').get('percent').items()
        v3pperc_str = ""
        for k,v in v3ppercents:
            v3pperc_str += f"{k}: {v}\n"

        output = f"{v3pwinner} {v3pcomment.lower()}\n{v3pperc_str}"
        # print(f"v3PERCENT::::::{v3ppercents}")
        await ctx.send(f"{ctx.message.author.mention}\n{output}")


def setup(bot):
    bot.add_cog(AdminCog(bot))