import glob
import os
from pathlib import Path

from lib.ScriptPatcher import ScriptPatcher
from lib.utils import load_mst

class TranslationProcessor:
	def __init__(self, patcher: ScriptPatcher, prefix: str, text_dir: Path):
		self.patcher = patcher
		self.prefix = prefix
		self.text_dir = text_dir

	def run(self) -> None:
		for name in glob.glob("**/*.mst", root_dir=self.text_dir, recursive=True):
			script = os.path.basename(name).removesuffix(".mst")
			entries = load_mst(self.text_dir / name)
			for index, text in entries.items():
				self.process_entry(script, index, text)

	def process_entry(self, script: str, index: int, text: str) -> None:
		if "\\lineRemove;" in text:
			if text != "\\lineRemove;":
				raise Exception(f"invalid translation line: {text}")
			self.patcher.add_mst_line(script, 1, index, "<REMOVED LINE PLACEHOLDER>")
			self.remove_mes(script, index)
			return
		parts = text.split("\\lineAdd;")
		if len(parts) < 2:
			self.patcher.add_mst_line(script, 1, index, text)
			return
		if index >= 10_000_000:
			raise Exception
		if index % 10 != 0:
			raise Exception
		if len(parts) > 11:
			raise Exception
		self.patcher.add_mst_line(script, 1, index, parts[0])
		new_indices = []
		for i, part in enumerate(parts[1:]):
			new_index = 30_000_000 + index + i
			self.patcher.add_mst_line(script, 1, new_index, part)
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
