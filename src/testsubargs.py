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
printer = subparser.add_parser('teams')
printer.add_argument('league', type=int, help="requires valid league ID")

printer = subparser.add_parser('players')
printer.add_argument('league', type=int, help="requires valid team ID and season")
# printer.set_defaults(func=printText)

cmd = parser.parse_args()
cmd.func(cmd)