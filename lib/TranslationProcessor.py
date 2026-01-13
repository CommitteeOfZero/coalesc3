# TODO: Documentation

import glob
import os
from pathlib import Path
import re

from lib.ScriptPatcher import ScriptPatcher
from lib.utils import load_mst
from lib.types import SaveMethod, ScriptFormat, Language, ScSPatch, ScSPatchLine

from typing import Literal, NamedTuple, assert_never

class TranslationProcessor:
    def __init__(self, patcher: ScriptPatcher, prefix: str, text_dir: Path):
        self.patcher = patcher
        self.prefix = prefix
        self.text_dir = text_dir

    def run(self) -> None:
        for name in glob.glob(f"**/*{ self.patcher.build_info.in_fmt }", root_dir=self.text_dir, recursive=True):
            script = os.path.basename(name).removesuffix(str(self.patcher.build_info.in_fmt))
            
            # Versioned script
            if any(script.startswith(stem) for stem in self.patcher.build_info.versioned):
                # Other platform OR retail versioned script that doesn't match
                if not script.endswith(f"_{ self.patcher.build_info.platform }") and \
                    not script.endswith(f"_{ self.patcher.build_info.platform[:3] }"): continue
                # Current platform, let retail versioned script through
                script = script.removesuffix(f"_{self.patcher.build_info.platform}")

            entries = load_mst(self.text_dir / name, self.patcher.build_info.line_inc, self.patcher.build_info.comments)
            for index, text in entries.items():
                self.process_entry(script, index, text, len(entries))

    def process_entry(self, script: str, index: int, text: str, num_entries: int) -> None:
        language: int = +self.patcher.build_info.selected

        if self.patcher.build_info.in_fmt == ScriptFormat.MST and re.match(r"_[0-9]{2}$", script):
            language = int(script[-2:])
            script = script[:-3]

        if "\\lineRemove;" in text:
            if text != "\\lineRemove;":
                raise Exception(f"invalid translation line: {text}")
            self.patcher.add_mst_line(script, 1, index, "<REMOVED LINE PLACEHOLDER>")
            self.remove_mes(script, index)
            return
        parts = text.split("\\lineAdd;")
        if len(parts) < 2:
            self.patcher.add_mst_line(script, language, index, text)
            return
        if index >= 10_000_000:
            raise Exception
        if len(parts) > 11:
            raise Exception
        self.patcher.add_mst_line(script, language, index, parts[0])
        new_indices : list[int] = []
        for i, part in enumerate(parts[1:]):
            new_index : int

            match self.patcher.build_info.line_inc:
                case 1:
                    new_index = num_entries + len(self.patcher.mst_patches[script][language]) - index - 1
                case 100:
                    new_index = 30_000_000 + index + i
                case _:
                    assert_never(self.patcher.build_info.line_inc)
            
            self.patcher.add_mst_line(script, language, new_index, part)
            new_indices.append(new_index)
        self.extend_mes(script, index, new_indices, self.patcher.build_info.selected)

    def remove_mes(self, script: str, index: int):
        patch = f"""@@ {script}.scs
\t*@ref(ra):
+\t\tIf $W($$SW_LANGUAGE) == 1, @label(end)
\t\tMesSetSavePointRL @ref(ra)
\t\tMessWindowOpen
\t\tMessWindowOpenedWait
\t\tMesVoiceWait
\t\tMesSetMesMsb 0, {index}
\t\tMesMain
+\t@label(end):
"""
        key = f"{self.prefix}{script}:{index}"
        self.patcher.add_patch(key, patch)

    # TODO: Double-check diff side-by-side once more to make sure patches match
    def extend_mes(self, script: str, index: int, new_indices: list[int], lang: Language | Literal["all"]) -> None:
        patch = ScSPatch()
        _A = ScSPatchLine.Helpers.A
        _N = ScSPatchLine.Helpers.N

        patch += f"@@ { script }.scs"

        match self.patcher.build_info.save_method:
            case SaveMethod.RA:
                if lang != Language.JAPANESE:
                    patch += _A("$W($$COZ_SAVEPOINT) = 0;") +    \
                            "*@ref(ra):"
                    
                    if self.patcher.build_info.out_fmt == ScriptFormat.MST:
                        patch += _A("If $W($$SW_LANGUAGE) != 1, @label(start)")
                    
                    for new_index in new_indices:
                        patch += _A(f"If $W($$COZ_SAVEPOINT) == {new_index}, @label(_{new_index})")

                InstructionSet = NamedTuple("InstructionSet", [("lookup", str), ("new_line_macro", str)])
                insts : InstructionSet

                match self.patcher.build_info.out_fmt:
                    case ScriptFormat.MST: insts = InstructionSet("MesSetMesMsb", "/MesMsbRA")
                    case ScriptFormat.SCT: insts = InstructionSet("MesSetMesScx", "/MesScxRA")
                    case _:
                        assert_never(self.patcher.build_info.out_fmt)
                
                if lang != Language.JAPANESE:
                    patch += _A("@label(start):")
                
                patch +=    _N("MesSetSavePointRL @ref(ra)") +  \
                            "MessWindowOpen" +                  \
                            "MessWindowOpenedWait" +            \
                            "MesVoiceWait" +                    \
                            f"{ insts.lookup } 0, { index }" +  \
                            "MesMain"
                
                if self.patcher.build_info.out_fmt == ScriptFormat.MST and lang != Language.JAPANESE:
                    patch += _A("If $W($$SW_LANGUAGE) != 1, @label(end)")
                
                for new_index in new_indices:
                    if lang != Language.JAPANESE:
                        patch +=    _A(f"$W($$COZ_SAVEPOINT) = { new_index };") +   \
                                    _A(f"@label(_{ new_index }):")

                    patch += _A(f"{ insts.new_line_macro } @ref(ra), 0, { new_index }")

                    if lang != Language.JAPANESE:
                        patch += _A(f"@label(end):")
                
            case SaveMethod.IP:
                patch +=    _N("MessWindowOpen") +          \
                            "MessWindowOpenedWait" +        \
                            "MesVoiceWait" +                \
                            f"MesSetMesScx 0, { index }" +  \
                            "MesMain"

                for new_index in new_indices:
                    patch += _A(f"/MesScx 0, { new_index }")

            case _:
                assert_never(self.patcher.build_info.save_type)

        key = f"{self.prefix}{script}:{index}"
        self.patcher.add_patch(key, str(patch))
