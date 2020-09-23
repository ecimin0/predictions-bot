import asyncio
import discord.ext.test as dpytest
import predictions_bot
import pytest

@pytest.fixture(scope='module')
def event_loop():
    return asyncio.get_event_loop()

@pytest.fixture(scope='module')
async def bot(event_loop):    
    bot = await predictions_bot.init(predictions_bot.credentials, predictions_bot.options, predictions_bot.token, predictions_bot.cogs, loop=event_loop)
    dpytest.configure(bot)
    return dpytest

@pytest.mark.asyncio
async def test_echo(bot):    
    msg = await bot.message("+echo test")
    print(msg.content)
    bot.verify_message("test", contains=True)

@pytest.mark.asyncio
async def test_predict_no_prediction(bot):
    msg = await bot.message("+predict")
    bot.verify_message("It looks like you didn't actually predict anything!", contains=True) 

@pytest.mark.asyncio
async def test_timezone(bot):
    msg = await bot.message("+timezone")
    bot.verify_message("Your current timezone is UTC", contains=True) 

@pytest.mark.asyncio
async def test_set_timezone_spaces(bot):
    msg = await bot.message("+timezone     Asia/Kolkata")
    bot.verify_message("Your timezone has been set to Asia/Kolkata", contains=True) 

@pytest.mark.asyncio
async def test_get_timezone(bot):
    msg = await bot.message("+timezone")
    bot.verify_message("Your current timezone is Asia/Kolkata", contains=True) 
