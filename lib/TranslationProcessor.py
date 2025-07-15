import glob
import os
from pathlib import Path

from lib.ScriptPatcher import ScriptPatcher
from lib.utils import load_mst

class TranslationProcessor:
	def __init__(self, patcher: ScriptPatcher, prefix: str, text_dir: Path, game: str, platform: str, versioned: list[str]):
		self.patcher = patcher
		self.prefix = prefix
		self.text_dir = text_dir
		self.game = game
		self.platform = platform
		self.versioned = versioned

	def run(self) -> None:
		for name in glob.glob(f"**/*{ self.patcher.in_fmt }", root_dir=self.text_dir, recursive=True):
			if any(os.path.basename(name).startswith(stem) for stem in self.versioned) and not os.path.basename(name).endswith(f"_{ self.platform[:3] }{ self.patcher.in_fmt }"):
				continue
			script = os.path.basename(name).removesuffix(self.patcher.in_fmt)
			if self.game != "chaos_child" or self.platform != "windows" or os.path.basename(name) != "_startup_win.sct":
				script = script.removesuffix(f"_{self.platform[:3]}")

			entries = load_mst(self.text_dir / name, self.patcher.line_inc)
			for index, text in entries.items():
				self.process_entry(script, index, text)

	def process_entry(self, script: str, index: int, text: str) -> None:
		language: int = 1

		if script.endswith("_00") or script.endswith("_01"):
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
		if index % 10 != 0:
			raise Exception
		if len(parts) > 11:
			raise Exception
		self.patcher.add_mst_line(script, language, index, parts[0])
		new_indices = []
		for i, part in enumerate(parts[1:]):
			new_index = 30_000_000 + index + i
			self.patcher.add_mst_line(script, language, new_index, part)
			new_indices.append(new_index)
		self.extend_mes(script, index, new_indices)

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

	def extend_mes(self, script: str, index: int, new_indices: list[int]):
		patch = ""

		patch += f"""@@ {script}.scs
+\t\t$W($$COZ_SAVEPOINT) = 0;
\t*@ref(ra):
+\t\tIf $W($$SW_LANGUAGE) != 1, @label(start)
"""

		for new_index in new_indices:
			patch += f"""+\t\tIf $W($$COZ_SAVEPOINT) == {new_index}, @label(_{new_index})
"""

		patch += f"""+\t@label(start):
\t\tMesSetSavePointRL @ref(ra)
\t\tMessWindowOpen
\t\tMessWindowOpenedWait
\t\tMesVoiceWait
\t\tMesSetMesMsb 0, {index}
\t\tMesMain
+\t\tIf $W($$SW_LANGUAGE) != 1, @label(end)
"""

		for new_index in new_indices:
			patch += f"""+\t\t$W($$COZ_SAVEPOINT) = {new_index};
+\t@label(_{new_index}):
+\t\t/MesMsbRA @ref(ra), 0, {new_index}
"""

		patch += f"""+\t@label(end):
"""

		key = f"{self.prefix}{script}:{index}"
		self.patcher.add_patch(key, patch)
