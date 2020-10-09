from discord.ext import commands

class TooManyResults(Exception):
    pass

class PleaseTellMeAboutIt(Exception):
    pass

class IsNotAdmin(commands.CheckFailure):
    pass
 