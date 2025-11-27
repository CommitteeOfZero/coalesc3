from schema import Schema, And, Use, Optional, Or # type: ignore

from .types import *

# TODO: Add comments to each field

YAML_SCHEMA = Schema(
    {
        Use(SupportedGame): {
            "platforms" : [{
                "name": And(str, len),
                "flag_set": And(str, len),
                "charset": And(str, len),
                Optional("string_unit_encoding", default = StringUnitEncoding.UInt16) : Use(StringUnitEncoding),
                "in_fmt": Use(ScriptFormat),
                "out_fmt": Use(ScriptFormat),
                Optional("line_inc", default = 100): Or(1, 100), # type: ignore
                Optional("archive", default = None): Use(ArchiveFormat),
                "save_method": Use(SaveMethod),
                "langs": [Use(Language)],
                Optional("multilang", default = False): bool,
                Optional("raw", default = list()): list[And(str, len)]
            }],
            Optional("versioned", default = list()): [And(str, len)],
            Optional("comments", default = list()): [And(str, len)]
        }
    }
)