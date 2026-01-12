"""
`lib.schema` specifies the schema used for the `games.yaml` specification file.
The current model allows a per-platform configuration for each supported game.
"""

from schema import Schema, And, Use, Optional

from .types import *

YAML_SCHEMA = Schema(
    {
        Use(SupportedGame): {
            "platforms" : [{
                # The name of the platform, purely for identification purposes.
                "name": And(str, len),
                # The name of the flag set to be supplied to MgsScriptTools.
                "flag_set": And(str, len),
                # The name of the charset to be supplied to MgsScriptTools.
                "charset": And(str, len),
                # Whether string units 16-bit or 32-bit wide, to be supplied to MgsScriptTools.
                Optional("string_unit_encoding", default = StringUnitEncoding.UInt16) : Use(StringUnitEncoding),
                # The script format the translated scripts use (.mst or .sct).
                "in_fmt": Use(ScriptFormat),
                # The script format being output (.mst or .sct, platform dependent).
                "out_fmt": Use(ScriptFormat),
                # Archive format being used both for the scripts being extracted, as well as
                # the output ones (either cpk, mpk, or none).
                Optional("archive", default = None): Use(ArchiveFormat),
                # The kind of save method the game uses (ip or ra).
                "save_method": Use(SaveMethod),
                # The language for which to build a patch, regardless of the original language being patched.
                "langs": [Use(Language)],
                # Whether files are expected to have a trailing numeric identifier for the respective language.
                # Game-specific, present in later titles.
                Optional("language_suffix", default = True): bool,
                # Whether the game allows switching between different languages.
                Optional("multilang", default = False): bool,
                # List of files to be replaced as a last step.
                # Consequently, any possible prior output under the same filename is ignored.
                # Useful for unconventional and unconditional patching of any file.
                Optional("raw", default = list()): list[And(str, len)]
            }],
            # List of script names (without extension) that are to be processed separately for each platform.
            # What this effectively does is ignore any scripts in this list *unless* they have a trailing string 
            # in the format `_<plat>` where `<plat>` is the name of the platform.
            Optional("versioned", default = list()): [And(str, len)],
            # List of strings that are to be used to detect and subsequently remove comments in the translation scripts.
            # A line will only be considered a match if it starts with any of these strings.
            Optional("comments", default = list()): [And(str, len)]
        }
    }
)