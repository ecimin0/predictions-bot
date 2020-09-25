import asyncio
import discord.ext.test as dpytest
import discord
import predictions_bot
import pytest
import re 

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
    bot.verify_message("test", contains=True)

@pytest.mark.asyncio
async def test_predict_no_prediction(bot):
    msg = await bot.message("+predict")
    bot.verify_message("It looks like you didn't actually predict anything!", contains=True) 

@pytest.mark.asyncio
async def test_predict_fgs(bot):
    msg = await bot.message("+predict 1-1 auba fgs")
    message = bot.get_message().content
    assert re.match(".*`\+predict 1-1 auba fgs`\n\n\*\*Score\*\*\nNone [a-zA-Z]+ 1 - 1 None [a-zA-Z]+\n\n\*\*Goal Scorers\*\*\nP. Aubameyang: 1 fgs.*", message, re.DOTALL)

@pytest.mark.asyncio
async def test_predict_fgs_without_fgs(bot):
    msg = await bot.message("+predict 1-1 auba")
    message = bot.get_message().content
    assert re.match(".*`\+predict 1-1 auba`\n\n\*\*Score\*\*\nNone [a-zA-Z]+ 1 - 1 None [a-zA-Z]+\n\n\*\*Goal Scorers\*\*\nP. Aubameyang: 1 fgs.*", message, re.DOTALL)

@pytest.mark.asyncio
async def test_predict_too_many_goal_scorers(bot):
    msg = await bot.message("+predict 1-1 auba 2x")
    message = bot.get_message().content
    assert not re.match("It looks like you have predicted Arsenal to score 1, but have included too many goal scorers:\nPrediction: `+predict 1-1 auba 2x`\nNumber of scorers predicted: 2 | Predicted goals scored: 1", message, re.DOTALL)

@pytest.mark.asyncio
async def test_predict_not_a_player(bot):
    msg = await bot.message("+predict 1-1 notaplayer fgs")
    bot.verify_message("Please try again, no player named notaplayer", contains=True) 

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

@pytest.mark.asyncio
async def test_rules(bot):
    msg = await bot.message("+rules")
    bot.verify_message("**Remember, we are only counting Arsenal goal scorers**", contains=True) 

@pytest.mark.asyncio
async def test_when_arsenal(bot):
    msg = await bot.message("+when arsenal")
    bot.verify_message("You are on the channel for the arsenal, we cannot play against ourselves.", contains=True)

@pytest.mark.asyncio
async def test_when_tottenham(bot):
    msg = await bot.message("+when tottenham")
    bot.verify_message("vs", contains=True)

@pytest.mark.asyncio
async def test_when_nobody(bot):
    msg = await bot.message("+when nobody")
    bot.verify_message("nobody does not seem to be a team I recognize.", contains=True)

@pytest.mark.asyncio
async def test_next(bot):
    msg = await bot.message("+next")
    message = bot.get_message().content
    assert re.match(".*?\n\*\*Next 2 matches:\*\*\n\n(.*?\n.*?vs.*?\n\w*, \d+? \w+ \d\d:\d\d \w{2} \w{3}\n?\n?){2}", message)   

@pytest.mark.asyncio
async def test_next_nine(bot):
    msg = await bot.message("+next 9")
    message = bot.get_message().content
    assert re.match(".*?\n\*\*Next 9 matches:\*\*\n\n(.*?\n.*?vs.*?\n\w*, \d+? \w+ \d\d:\d\d \w{2} \w{3}\n?\n?){9}", message)   

@pytest.mark.asyncio
async def test_next_eleven(bot):
    msg = await bot.message("+next 11")
    message = bot.get_message().content
    assert re.match(".*?\n\*\*Next 11 matches:\*\*\n\n(.*?\n.*?vs.*?\n\w*, \d+? \w+ \d\d:\d\d \w{2} \w{3}\n?\n?){11}", message)  

@pytest.mark.asyncio
async def test_next_negative(bot):
    msg = await bot.message("+next -1")
    bot.verify_message("Number of next matches cannot be a negative number", contains=True)
 