#!/usr/local/bin/python3


# Predict our next match against West Ham United (A)
# Rules
# :two: points – correct result (w/d/l)
# :two: points – correct number of Arsenal goals
# :one: point – correct number of goals we concede
# :one: point – every correct scorer
# :one: point – correct FGS (only Arsenal)
# :two: points bonus – getting all scorers right

# No points for scorers if your prediction's goals exceed the actual goals by 4+.

# Remember, we are only counting Arsenal goal scorers so you do not need to predict who scored for the opposition team
# also applies to FGS.

# Example
# +predict 4:0 auba 2x fgs, laca, mustafi


# pip3 install discord
import discord
from discord.ext import commands
import re


# MAKE THIS AN ENVIRONMENT VARIABLE SOON
token = "NjM3NzQ5Mjg1OTk1NDEzNTA1.XeqgWA.SyRF0igSotR0JI-EdM-xdhHa0mI"


prefix = "+"
bot = commands.Bot(prefix)

@bot.event
# on_ready = connected to server
async def on_ready(): 
    print('Connected as {0.user}'.format(bot))


@bot.event
async def on_message(message):
    # if the bot sends messages to itself, don't return anything
    if message.author == bot.user:
        return
    print("Message content:", message.content)
    await bot.process_commands(message)

@bot.command()
async def predict(ctx):
    print(ctx.message.content)

@bot.command()
async def ping(ctx):
    '''
    This text will be shown in the help command
    '''

    # Get the latency of the bot
    latency = bot.latency  # Included in the Discord.py library
    # Send it to the user
    await ctx.send(latency)


@bot.command()
async def echo(ctx, *, content:str):
    await ctx.send(content)

# 'token' is your bot token
bot.run(token)  




# client = discord.Client()
# @client.event
# async def on_ready():
#     print('We have logged in as {0.user}'.format(client))
# @client.event
# async def on_message(message):
#     if message.author == client.user:
#         return
#     if message.content.startswith('$hello'):
#         await message.channel.send('Hello!')
# client.run(token)