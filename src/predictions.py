#!/usr/local/bin/python3

# pip3 install discord
import discord
from discord.ext import commands
import re
import sys


# Predict our next match against West Ham United (A)
rules_set = """Prediction League Rules:

2 points – correct result (W/D/L)
2 points – correct number of Arsenal goals
1 point – correct number of goals conceded
1 point – each correct scorer
1 point – correct FGS (first goal scorer, only Arsenal)
2 points bonus – correct all scorers

No points for scorers if your prediction's goals exceed the actual goals by 4+

Remember, we are only counting Arsenal goal scorers so you do not need to 
predict who scored for the opposition team. This also applies to FGS.

Example:
+predict 3:0 auba 2x fgs, laca
"""

# MAKE THIS AN ENVIRONMENT VARIABLE SOON
token = "NjM3NzQ5Mjg1OTk1NDEzNTA1.XeqgWA.SyRF0igSotR0JI-EdM-xdhHa0mI"

prefix = "+"
# bot = commands.Bot(prefix)

help_function = commands.DefaultHelpCommand(no_category="Available Commands", indent=4)
bot = commands.Bot(prefix, help_command=help_function)


### Bot Events ###
@bot.event
# on_ready = connected to server
async def on_ready(): 
    print('Connected as {0.user}'.format(bot))


@bot.event
async def on_message(message):
    # if the bot sends messages to itself, don't return anything
    if message.author == bot.user:
        return
    print(f"@{message.author} Message content: {message.content}")

    await bot.process_commands(message)


### Bot Commands ###
# rules
@bot.command()
async def rules(ctx):
    '''
    Display Prediction League Rules
    '''
    await ctx.send(f"{ctx.message.author.mention}\n{rules_set}")


# predict
@bot.command()
async def predict(ctx):
    '''
    Make a new prediction
    '''
    print(ctx.message.content)


# show user's predictions
@bot.command()
async def predictions(ctx):
    '''
    Show your past predictions
    '''

# show leaderboard
@bot.command()
async def leaderboard(ctx):
    '''
    Show leaderboard
    '''        

# change timezone
@bot.command()
async def timezone(ctx):
    '''
    Change timezone
    '''

# next 2 matches of each competition
@bot.command()
async def next(ctx):
    '''
    Next 2 matches in each competition
    '''

# list fixtures
@bot.command()
async def fixtures(ctx):
    '''
    Full fixture list
    '''

# show match vs specific team
@bot.command()
async def when(ctx):
    '''
    Return next match against given team | when <team>
    '''        

# results
@bot.command()
async def results(ctx):
    '''
    Return historical match results
    '''        

# PL table
@bot.command()
async def table(ctx):
    '''
    Current Premier League table
    '''        

# CL table
@bot.command()
async def cltable(ctx):
    '''
    Current Champion's League table
    '''        

# EL table
@bot.command()
async def eltable(ctx):
    '''
    Current Europa League table
    '''

# ping
@bot.command()
async def ping(ctx):
    '''
    Return latency between bot and server
    '''
    # Get the latency of the bot
    # Included in the Discord.py library
    latency = bot.latency
    # Send it to the user
    await ctx.send(f"{ctx.message.author.mention}\n{latency}")


# echo (mostly for testing)
@bot.command(hidden=True)
async def echo(ctx, *, content:str):
    '''
    Repeat what you typed (for testing/debugging)
    '''    
    await ctx.send(content)


# tottenham is shit
@bot.command(hidden=True)
async def what_do_you_think_of_tottenham(ctx):
    '''
    Who do we think is shit?
    '''
    video = "https://www.youtube.com/watch?v=w0R7gWf-nSA"
    spurs_status = "SHIT"    
    await ctx.send(f"{ctx.message.author.mention}\n{spurs_status}\n{video}")


# bot.load_extension("cogs.MainCog")

# 'token' is the bot token from Discord Developer config
try:
    bot.run(token)  
except Exception as e:
    print(f"error: {e}")
    sys.exit(1)
    