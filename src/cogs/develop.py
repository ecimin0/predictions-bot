import asyncio
import discord
from discord.ext import commands

from utils.exceptions import *
from typing import List, Union, Mapping

class DevelopCog(commands.Cog): # type: ignore

    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    async def cog_check(self, ctx: commands.Context):
        if ctx.message.author.id in self.bot.admin_ids:
            return True
        else:
            raise IsNotAdmin(f"User {ctx.message.author.name} is not an admin and cannot use this function.")

    @commands.command(hidden=True)
    async def getEmoji(self, ctx: commands.Context):
        emojis: List[str] = []
            # .emojis.forEach(emoji => console.log(emoji.animated ? '<a:' + emoji.name + ':' + emoji.id + '>' : '<:' + emoji.name + ':' + emoji.id + '>'));
        for emoji in ctx.guild.emojis:
            emojis.append(f"{str(emoji)}  {emoji.name}  {str(emoji.id)}")
        # emoji_list = tabulate(emojis, tablefmt="plain")
        # emoji_list = sorted(emojis)
        emoji_list = "\n".join(emojis)
        output = f'{emoji_list}'
        await ctx.send(output)


    @commands.command(hidden=True)
    async def testEmbed(self, ctx: commands.Context):
        '''
        Generate a test embed object
        '''
        # log = logger.bind(content=ctx.message.content, author=ctx.message.author)
        paginated_data: List[Mapping] = [
            {"title": "Test 0", "msg": "TestMessage 0"}, 
            {"title": "Test 1", "msg": "TestMessage 1"},
            {"title": "Test 2", "msg": "TestMessage 2"}
        ]
        max_page = len(paginated_data) - 1
        num = 0
        first_run = True
        while True:
            # log.info(num=num, max_page=max_page)
            if first_run:
                embedVar = discord.Embed(title=paginated_data[num].get("title"), description="Desc", color=0x9c824a)
                embedVar.add_field(name=f"Test {num}", value=paginated_data[num].get("msg"), inline=False)

                first_run = False
                msg = await ctx.send(embed=embedVar)

            reactmoji = []
            if max_page == 0 and num == 0:
                pass
            elif num == 0:
                reactmoji.append('⏩')
            elif num == max_page:
                reactmoji.append('⏪')
            elif num > 0 and num < max_page:
                reactmoji.extend(['⏪', '⏩'])
            # reactmoji.append('✅')

            for react in reactmoji:
                await msg.add_reaction(react)

            def checkReact(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=checkReact)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()

            if user != ctx.message.author:
                pass
            elif '⏪' in str(res.emoji):
                print('<< Going backward')
                num = num - 1
                embedVar = discord.Embed(title=paginated_data[num].get("title"), description="Desc", color=0x9c824a)
                embedVar.add_field(name=f"Test {num}", value=paginated_data[num].get("msg"), inline=False)
                await msg.clear_reactions()
                await msg.edit(embed=embedVar)

            elif '⏩' in str(res.emoji):
                print('\t>> Going forward')
                num = num + 1
                embedVar = discord.Embed(title=paginated_data[num].get("title"), description="Desc", color=0x9c824a)
                embedVar.add_field(name=f"Test {num}", value=paginated_data[num].get("msg"), inline=False)
                await msg.clear_reactions()
                await msg.edit(embed=embedVar)


    @commands.command(hidden=True)
    async def testPage(self, ctx):
        '''
        Generate a test embed object
        '''
        # log = logger.bind(content=ctx.message.content, author=ctx.message.author)
        paginated_data = [
            {"title": "Test 0", "msg": "TestMessage 0"}, 
            {"title": "Test 1", "msg": "TestMessage 1"},
            {"title": "Test 2", "msg": "TestMessage 2"}
        ]
        max_page = len(paginated_data) - 1
        num = 0
        first_run = True
        while True:
            # log.info(num=num, max_page=max_page)
            if first_run:
                # embedVar = discord.Embed(title=paginated_data[num].get("title"), description="Desc", color=0x9c824a)
                # embedVar.add_field(name=f"Test {num}", value=paginated_data[num].get("msg"), inline=False)

                first_run = False
                msg = await ctx.send(f"{paginated_data[num]}")

            reactmoji = []
            if max_page == 0 and num == 0:
                pass
            elif num == 0:
                reactmoji.append('⏩')
            elif num == max_page:
                reactmoji.append('⏪')
            elif num > 0 and num < max_page:
                reactmoji.extend(['⏪', '⏩'])
            # reactmoji.append('✅')

            for react in reactmoji:
                await msg.add_reaction(react)

            def checkReact(reaction, user):
                if reaction.message.id != msg.id:
                    return False
                if user != ctx.message.author:
                    return False
                if str(reaction.emoji) not in reactmoji:
                    return False
                return True

            try:
                res, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=checkReact)
            except asyncio.TimeoutError:
                return await msg.clear_reactions()

            if user != ctx.message.author:
                pass
            elif '⏪' in str(res.emoji):
                print('<< Going backward')
                num = num - 1
                # embedVar = discord.Embed(title=paginated_data[num].get("title"), description="Desc", color=0x9c824a)
                # embedVar.add_field(name=f"Test {num}", value=paginated_data[num].get("msg"), inline=False)
                await msg.clear_reactions()
                # await msg.edit(embed=embedVar)
                await msg.edit(content=f"{paginated_data[num]}")

            elif '⏩' in str(res.emoji):
                print('\t>> Going forward')
                num = num + 1
                # embedVar = discord.Embed(title=paginated_data[num].get("title"), description="Desc", color=0x9c824a)
                # embedVar.add_field(name=f"Test {num}", value=paginated_data[num].get("msg"), inline=False)
                await msg.clear_reactions()
                # await msg.edit(embed=embedVar)
                await msg.edit(content=f"{paginated_data[num]}")


def setup(bot):
    bot.add_cog(DevelopCog(bot))