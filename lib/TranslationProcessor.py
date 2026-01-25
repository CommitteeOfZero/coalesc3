# TODO: Documentation

import glob
import os
from pathlib import Path
import re

from lib.ScriptPatcher import ScriptPatcher
from lib.utils import load_mst
from lib.types import SaveMethod, ScriptFormat, Language

from typing import assert_never, Literal

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
		assert self.patcher.build_info.selected != "all", "Multilang games must have their languages processed individually"

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
		voiced : bool = re.match(r"([0-9]+:)?〔", parts[0]) is not None
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
		self.extend_mes(script, index, voiced, new_indices, self.patcher.build_info.selected)

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

	def extend_mes(self, script: str, index: int, voiced : bool, new_indices: list[int], lang: Language | Literal["all"]):
		patch = f"""@@ {script}.scs
"""

		match self.patcher.build_info.save_method:
			case SaveMethod.RA:
				if lang != Language.JAPANESE:
					patch += f"""+\t\t$W($$COZ_SAVEPOINT) = 0;
\t*@ref(ra):
{ "+\t\tIf $W($$SW_LANGUAGE) != 1, @label(start)\n" if self.patcher.build_info.out_fmt == ScriptFormat.MST else "" }"""

					for new_index in new_indices:
						patch += f"""+\t\tIf $W($$COZ_SAVEPOINT) == {new_index}, @label(_{new_index})
"""

				insts : tuple[str, str, str]
				match self.patcher.build_info.out_fmt:
					case ScriptFormat.MST: insts = ("MesSetMesMsb", "/MesMsbRA", "Mes2VSetMesMsb")
					case ScriptFormat.SCT: insts = ("MesSetMesScx", "/MesScxRA", "Mes2VSetMesScx")
				
				if lang != Language.JAPANESE:
					patch += f"""+\t@label(start):
"""
				
				patch += f"""\t\tMesSetSavePointRL @ref(ra)
\t\tMessWindowOpen
\t\tMessWindowOpenedWait
\t\tMesVoiceWait
\t\t{ f"{ insts[0] } 0," if not voiced else f"{ insts[2] } @ignore, @ignore, @ignore," } { index }
\t\tMesMain
{ "+\t\tIf $W($$SW_LANGUAGE) != 1, @label(end)\n" if self.patcher.build_info.out_fmt == ScriptFormat.MST and lang != Language.JAPANESE else "" }"""

				for new_index in new_indices:
					if lang != Language.JAPANESE:
						patch += f"""+\t\t$W($$COZ_SAVEPOINT) = {new_index};
+\t@label(_{new_index}):
"""

					patch += f"""+\t\t{insts[1]} @ref(ra), 0, {new_index}
"""
				if self.patcher.build_info.out_fmt == ScriptFormat.MST and lang != Language.JAPANESE:
					patch += f"""+\t@label(end):
"""
				
			case SaveMethod.IP:
				patch += f"""\t\tMesSetSavePoint
\t\tMessWindowOpen
\t\tMessWindowOpenedWait
\t\tMesVoiceWait
\t\tMesSetMesScx 0, {index}
\t\tMesMain
"""
				for new_index in new_indices:
					patch += f"+\t/MesScx 0, {new_index}\n"

			case _:
				assert_never(self.patcher.save_type)

		key = f"{self.prefix}{script}:{index}"
		self.patcher.add_patch(key, patch)
