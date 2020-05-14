#!/usr/local/bin/python3

import argparse

# parser = argparse.ArgumentParser(description="Runs the script")

# subparsers = parser.add_subparsers(help='Specify secondary options')

# parser.add_argument("--all", type=str, help="Primary Arguments")

# secondary_parser = subparsers.add_parser('secondary', help='secondary options')

# secondary_parser.add_argument('-o', '--one', help='Sub-argument one', action='store_true') 

# secondary_parser.add_argument('-t', '--two', help='Sub-argument two', action='store_true') 

# args = parser.parse_args()


# def printText(args):
#   print(args)

parser = argparse.ArgumentParser(description="Populate database with info from football API")
subparser = parser.add_subparsers()
printer = subparser.add_parser('countries')
printer.add_argument('n/a', type=int, help="no parameters required; get all country names and codes")

printer = subparser.add_parser('leagues')
printer.add_argument('<season>', type=int, help="season string: e.g. '2019' is valid for the 2019-2020 season; get specified season's league IDs to db")

printer = subparser.add_parser('teams')
printer.add_argument('<league ID>', type=int, help="league ID; check leagues in db for reference; get teams by league")

printer = subparser.add_parser('players')
printer.add_argument('players', type=int, help="team ID and season")

printer = subparser.add_parser('fixtures')
printer.add_argument('fixtures', type=int, help="requires valid team ID and season")

printer = subparser.add_parser('tables')
printer.add_argument('tables', type=int, help="requires valid team ID and season")
# printer.set_defaults(func=printText)

cmd = parser.parse_args()
cmd.func(cmd)