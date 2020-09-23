import asyncpg
import discord
from discord.ext import commands
from tabulate import tabulate
from utils.exceptions import *
from utils.utils import isAdmin

class AdminCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.message.author.id in self.bot.admin_ids:
            return True
        else:
            raise IsNotAdmin(f"User {ctx.message.author.name} is not an admin and cannot use this function.")

       
    @commands.command(name='list_cogs', hidden=True)
    async def list_cogs(self, ctx):
        output = ""
        for cog in self.bot.cogs:
            output += f"{cog}\n"
        await ctx.send(output) 
        

    @commands.command(name='load', hidden=True)
    async def load(self, ctx, *, cog: str):
        """Command which Loads a Module.
        Remember to use dot path. e.g: cogs.owner"""

        try:
            self.bot.load_extension(cog)
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('**`SUCCESS`**')

    @commands.command(name='unload', hidden=True)
    async def unload(self, ctx, *, cog: str):
        """Command which Unloads a Module.
        Remember to use dot path. e.g: cogs.owner"""

        try:
            self.bot.unload_extension(cog)
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('**`SUCCESS`**')

    @commands.command(hidden=True)
    async def userLookup(self, ctx, *input_str:str):
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

    @commands.command(hidden=True)
    async def messageLookup(self, ctx, input_id:int):
        '''
        Return message ID and ID of message author
        '''
        id_to_lookup = input_id
        output = None
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

    @commands.command(hidden=True)
    async def addNickname(self, ctx, nicknameType:str, id:int, nickname:str):
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

    @commands.command(hidden=True)
    async def removeNickname(self, ctx, nicknameType:str, id:int, nickname:str):
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

    @commands.command(hidden=True)
    async def listPlayers(self, ctx):
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

def setup(bot):
    bot.add_cog(AdminCog(bot))