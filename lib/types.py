"""
`lib.types`, as the name implies, are where the types used across coalesc3 are defined.
"""

from __future__ import annotations

from enum import StrEnum, auto
from dataclasses import dataclass

from functools import reduce
from operator import add

from typing import Self, Literal, Any, cast, assert_never

from argparse import Namespace

class Extension:
    """
    Simple helper class for preprending subclasses of `str` with a dot
    to mimic file extension notation.
    """
    def __str__(self : Self):
        return f".{ super().__str__() }"

class ScriptFormat(Extension, StrEnum):
    """
    String enum used for distinguishing from different script formats.
    - `.sct`: Strings are stored alongside the instructions, which by definition
    does not allow multiple languages, as the script would have to be replaced wholesale.
    Line IDs are stored in increments of `1`, and ***must*** all be consecutive.
    (They are likely treated as index in an array of file offsets, instead of a sparse mapping.)
    - `.mst`: Strings are stored in separate files, allowing for choosing between different
    languages as runtimes, thanks to the one-to-many mapping from line ID to text (one per language).
    Line IDs are stored in increments of `100`, with intermediate values used for extending lines
    across languages/versions/platforms.
    """
    SCT = auto()
    MST = auto()

class SaveMethod(StrEnum):
    """
    String enum used for distinguishing from different save methods.
    - `IP`: Acronym for "instruction pointer." Game versions with this save method store the progress
    at any given script as a file offset, making certain changes to the script (such as adding lines)
    rather impractical, as they make save files no longer forwards-compatible with unpatched versions
    of the game.
    - `RA`: Acronym for "return address." Game versions with this save method store the progress at any
    given script as the number assigned to the return label corresponding to the save point. As this is
    not a hard value written to the save file, and the correct file offset is only looked up at runtime,
    forward-compatibility can be achieved through a custom savepoint stored in a global variable (taken 
    care of by our macros).
    """
    IP = auto()
    RA = auto()

class Language(StrEnum):
    """
    String enum used for distinguishing between game languages.
    As each language as a given numeric ID shared between games, this allows the tool to correctly (re)name
    files as necessary.
    """
    JAPANESE = "jpn"
    ENGLISH = "eng"
    def __int__(self) -> int:
        return list(self.__class__.__members__.keys()).index(self.name)
    def __pos__(self) -> int:
        return int(self)
    
class ArchiveFormat(Extension, StrEnum):
    """
    String enum used for distinguishing between the different archive formats used across the many different
    MAGES. Engine games.
    Depending on game version, either CPK (by CRI Middleware), MPK, or no archive format may be used (meaning
    the files are stored in folders with the same name as the otherwise would-be archives).
    """
    CPK = auto()
    MPK = auto()

class SupportedGame(StrEnum):
    """
    As the name implies, this is the list of the supported games for coalesc3.
    While trivial to add an entry to the enum, only the ones present here are 
    guaranteed (or generally expected) to work, as each new game added as a target
    invariably involves work on the tool itself, as each game has different needs
    one can only do so much to predict.
    """
    CHAOS_HEAD = auto()
    CHAOS_CHILD = auto()
    CHAOS_HEAD_LCC = auto()
    CHAOS_CHILD_LCC = auto()

class StringUnitEncoding(StrEnum):
    """
    String enum used for determining the bit width of the string units for a specific game version.
    In other words, how many bits a character takes up in any given Sc3 VM string for that game version.
    """
    UInt16 = "UInt16"
    UInt32 = "UInt32"

@dataclass(kw_only = True)
class BuildInfo:
    """
    This dataclass is used to pass around aggregate information about
    the current build gathered from both `YAML_SCHEMA` (filled from `data/games.yaml`),
    as well as the arguments supplied for the program.

    For more information on each member variable, refer to `lib.schema`.
    """
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
        
        line_inc : Literal[1, 100]
        match cast(ScriptFormat, initializer["out_fmt"]):
            case ScriptFormat.MST: line_inc = 100
            case ScriptFormat.SCT: line_inc = 1
            case _:
                assert_never(initializer["out_fmt"])
        initializer["line_inc"] = line_inc

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

@dataclass(frozen = True, init = False)
class ScSPatchLine(str):
    class Kind(StrEnum):
        REMOVAL  =  "-"
        NEUTRAL  =  ""
        ADDITION =  "+"        

    class Helpers:
        @staticmethod
        def _A(line : str) -> ScSPatchLine:
            return +ScSPatchLine(line)
        
        @staticmethod
        def _R(line : str) -> ScSPatchLine:
            return -ScSPatchLine(line)
    
    kind : Kind
    
    def __new__(cls : type[Self], patch : str | None = None) -> Self:
        assert patch is None or isinstance(patch, str), f"Expected 'str', got '{ type(patch).__name__ }'"
        
        if isinstance(patch, str) and len(patch.split("\n")) > 1:
            raise ValueError("Argument string must be one line only")
        
        return super().__new__(cls, patch if patch is not None else "")
    
    def __init__(self : Self, patch : str | None = None) -> None:
        super().__setattr__("kind", ScSPatchLine.Kind.NEUTRAL if not isinstance(patch, ScSPatchLine) else patch.kind)

    def __pos__(self : Self) -> ScSPatchLine:
        ret = ScSPatchLine(super().__str__())
        super(str, ret).__setattr__("kind", ScSPatchLine.Kind.ADDITION)
        return ret

    def __neg__(self : Self) -> ScSPatchLine:
        ret = ScSPatchLine(super().__str__())
        super(str, ret).__setattr__("kind", ScSPatchLine.Kind.REMOVAL)
        return ret

    def __str__(self : Self) -> str:
        return f"{ self.kind }\t{ "\t" if not self.rstrip().endswith(":") else "" }{ super().__str__() }\n"

class ScSPatch:
    def __init__(self : Self, other : None | ScSPatch = None):
        assert other is None or isinstance(other, ScSPatch), f"Expected 'None' or '{ self.__class__.__name__ }', got { type(other).__name__ }"
        self.patch_lines : list[ScSPatchLine] = other.patch_lines.copy() if other is not None else []

    def add_or_concat(self : Self, other : Any, inplace : bool) -> ScSPatch | None:
        if not isinstance(other, str) and not isinstance(other, ScSPatch):
            raise TypeError(f"unsupported operand type(s) for +: '{ self.__class__.__name__ }' and '{ type(other).__name__ }'")
        
        ret = None if inplace else ScSPatch(self)
        
        if isinstance(other, ScSPatch): (ret or self).patch_lines += other.patch_lines
        elif isinstance(other, ScSPatchLine): (ret or self).patch_lines.append(other)
        else: (ret or self).patch_lines.append(ScSPatchLine(other))

        return ret

    def __add__(self : Self, other : Any) -> ScSPatch:
        return cast(ScSPatch, self.add_or_concat(other, False))
    
    def __iadd__(self : Self, other : Any) -> None:
        self.add_or_concat(other, True)
    
    def __str__(self : Self) -> str:
        return reduce(add, map(str, self.patch_lines), "")

