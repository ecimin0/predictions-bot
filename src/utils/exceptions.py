from discord.ext import commands


class PleaseTellMeAboutIt(Exception):
    pass

class IsNotAdmin(commands.CheckFailure):
    pass

class RateLimit(commands.CheckFailure):
    pass    