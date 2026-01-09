from enum import StrEnum, auto
from dataclasses import dataclass

from typing import Self, Literal, Any

from argparse import Namespace

class Extension:
    def __str__(self : Self):
        return f".{ super().__str__() }"

class ScriptFormat(Extension, StrEnum):
    SCT = auto()
    MST = auto()

class SaveMethod(StrEnum):
    IP = auto()
    RA = auto()

class Language(StrEnum):
    JAPANESE = "jpn"
    ENGLISH = "eng"
    def __int__(self) -> int:
        return list(self.__class__.__members__.keys()).index(self.name)
    def __pos__(self) -> int:
        return int(self)
    
class ArchiveFormat(Extension, StrEnum):
    CPK = auto()
    MPK = auto()

class SupportedGame(StrEnum):
    CHAOS_HEAD = auto()
    CHAOS_CHILD = auto()
    CHAOS_HEAD_LCC = auto()
    CHAOS_CHILD_LCC = auto()
    STEINS_GATE_HD = auto()

class StringUnitEncoding(StrEnum):
    UInt16 = "UInt16"
    UInt32 = "UInt32"

@dataclass(kw_only = True)
class BuildInfo:
    game        : SupportedGame
    platform    : str
    flag_set    : str
    charset     : str
    string_unit_encoding : StringUnitEncoding
    in_fmt      : ScriptFormat
    out_fmt     : ScriptFormat
    line_inc    : Literal[1, 100]
    archive     : ArchiveFormat | None
    save_method : SaveMethod
    selected    : Language | Literal["all"]
    langs       : list[Language]
    language_suffix : bool
    versioned   : list[str]
    comments    : list[str]
    raw         : list[str]
    clean       : bool

    @staticmethod
    def from_validated(spec : dict[str, Any], args : Namespace):
        initializer = get_platform_spec(spec[args.game]["platforms"], args.platform)

        initializer.pop("multilang")

        initializer["game"] = SupportedGame(args.game)
        initializer["selected"] = Language(args.lang) if args.lang in Language else args.lang 
        initializer["platform"] = initializer.pop("name")
        initializer["versioned"] = spec[args.game]["versioned"]
        initializer["comments"] = spec[args.game]["comments"]
        initializer["clean"] = args.clean

        return BuildInfo(**initializer)
    

def get_platform_spec(platform_specs: list[dict[str, Any]], platform : str) -> dict[str, Any]:
    for current in platform_specs:
        if current["name"] != platform: continue
        return current
    else:
        assert False, "Unreachable"