from argparse import ArgumentParser, ArgumentError, Namespace

from typing import Any
from operator import itemgetter

from .types import *

class ArgumentParserHandler:
    def __init__(self : Self):
        self.arg_parser = ArgumentParser()

        self.arg_parser.add_argument(
            "--clean",
            action="store_const",
            const=True,
            dest="clean",
            default=False,
            help="Clear cache and build from scratch."
        )

        self.arg_parser.add_argument(
            metavar="GAME",
            dest="game",
            choices=(*map(str, SupportedGame.__members__.values()),),
            help="Game to build patch for."
        )

        self.arg_parser.add_argument(
            metavar="PLATFORM",
            dest="platform",
            help="Platform to build patch for."
	    )

        self.arg_parser.add_argument(
            metavar="LANG",
            dest="lang",
            choices=(*map(str, Language.__members__.values()), "all"),
            help="Language to build patch for (use 'all' for multi-language configurations)."
	    )

    def validate_against_spec(self : Self, spec : dict[str, Any]) -> Namespace:
        args = self.arg_parser.parse_args()

        if args.platform not in map(itemgetter("name"), spec[args.game]["platforms"]):
            raise ArgumentError(None, f"Game '{ args.game }' has no configuration for platform '{ args.platform }'.")
        
        platform_spec = get_platform_spec(spec[args.game]["platforms"], args.platform)

        if args.lang != "all" and platform_spec["multilang"]:
            raise ArgumentError(None, f"Game '{ args.game }' for platform '{ args.platform }' only supports the 'all' language option.")
        
        if args.lang == "all" and not platform_spec["multilang"]:
            raise ArgumentError(None, f"Game '{ args.game }' for platform '{ args.platform }' does not support multilanguage building.")

        if args.lang != "all" and args.lang not in platform_spec["langs"]:
            raise ArgumentError(None, f"Game '{ args.game }' for platform '{ args.platform }' doesn't support language '{ args.lang }'.")

        return args
    

