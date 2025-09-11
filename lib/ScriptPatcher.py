from pathlib import Path
import re
from typing import Optional, Callable, Self

from lib.config import (
	PATCHSCS_PATH,
)
from lib.utils import load_mst, save_mst, run_command
from lib.types import ScriptFormat, BuildInfo

class ScriptPatcher:
	def __init__(self : Self, scs_dir: Path, build_dir: Path, consts: dict[str, str], build_info : BuildInfo):
		self.scs_dir     : Path = scs_dir
		self.build_dir   : Path = build_dir
		self.consts      : dict[str, str] = consts
		self.build_info  : BuildInfo = build_info
		self.scs_patches : list[tuple[str, str]] = []
		self.mst_patches : dict[str, dict[int, dict[int, str]]] = {}

	def add_patch(self, key: str, text: str) -> None:
		text = PatchPreprocessor(self, text).run()
		self.scs_patches.append((key, text))

	def add_mst_line(self, script: str, language: int, index: int, text: str) -> None:
		if script not in self.mst_patches:
			self.mst_patches[script] = {}
		script_table = self.mst_patches[script]

		if language not in script_table:
			script_table[language] = {}
		language_table = script_table[language]

		if index in language_table:
			raise Exception(f"line ID conflict: {language:02}:{index}")
		language_table[index] = text

	def run(self) -> None:
		self._apply_scs_patches()
		self._apply_mst_patches()

	def _apply_scs_patches(self) -> None:
		patch_path = self.build_dir / "combined.patch"
		with open(patch_path, "w", encoding="utf-8") as f:
			for (_, text) in sorted(self.scs_patches, key=lambda x: x[0]):
				f.write(f"{text}\n\n")
		run_command(
			PATCHSCS_PATH,
			self.scs_dir,
			patch_path,
		)

	def _apply_mst_patches(self) -> None:
		for script, script_table in self.mst_patches.items():
			for language, language_table in script_table.items():
				mst_path: Path
				match self.build_info.out_fmt:
					case ScriptFormat.MST:
						mst_path = self.scs_dir / f"mes{language:02}/{script}_{language:02}.mst"
					case ScriptFormat.SCT:
						mst_path = self.scs_dir / f"{script}.sct"

				entries = load_mst(mst_path, self.build_info.line_inc)

				if entries.keys() != language_table.keys() and \
				   len(entries) == len(language_table) and \
				   self.build_info.out_fmt != self.build_info.in_fmt:
					assert self.build_info.out_fmt == ScriptFormat.MST, "Error: line numbering fix is only implemented for .sct -> .mst"
					diffs = list(filter(lambda key : key % self.build_info.line_inc != 0, entries.keys()))
					for diff in diffs:
						offset = diff % self.build_info.line_inc
						old_index = (diff - offset) + offset * 10
						language_table[diff] = language_table.pop(old_index)
						for index in list(filter(lambda x : x > old_index, language_table.keys())):
							language_table[index - self.build_info.line_inc] = language_table.pop(index)
				
				if entries.keys() != language_table.keys() and self.build_info.out_fmt != self.build_info.in_fmt:
					print(f"Warning: translation patch for { script } has a different number of lines "
		                    "than expected. Please check manually.")
					
				entries.update(language_table)
				save_mst(mst_path, entries)

MACRO_TABLE : dict[str, Callable[["PatchPreprocessor", str], str]] = {}

def macro(name: Optional[str] = None):
	def inner(fn: Callable[["PatchPreprocessor", str], str]):
		actual_name = name
		if actual_name is None:
			actual_name = fn.__name__
		MACRO_TABLE[actual_name] = fn
	return inner

class PatchPreprocessor:
	def __init__(self, patcher: ScriptPatcher, text: str):
		self.patcher = patcher
		self.lines = text.splitlines()
		self.offset = 0
		self.name: Optional[str] = None
		self.label_count: Optional[int] = None
		self.ra_count: Optional[int] = None

	def run(self) -> str:
		while self.offset < len(self.lines):
			self.process_line()
		return "\n".join(self.lines)

	def process_line(self) -> None:
		text = self.lines[self.offset]
		if text.startswith("@@"):
			self.name = text[2:].strip()
			self.label_count = 0
			self.ra_count = 0
		if not text.startswith("#"):
			text = self.process_tags(text)
			self.lines[self.offset] = text
		if not text.startswith("+"):
			self.offset += 1
			return
		text = text[1:].lstrip()
		if text[:1] != "/":
			self.offset += 1
			return
		if self.name is None:
			raise Exception("macro before patch start")
		self.lines.pop(self.offset)
		macro = text[1:]
		offset = self.offset
		try:
			lines = self.process_macro(macro).splitlines()
		except Exception as e:
			raise Exception(e, macro)
		for line in lines:
			line = line.rstrip()
			if not line:
				continue
			self.lines.insert(offset, f"+\t{line}")
			offset += 1

	def process_tags(self, text: str) -> str:
		while True:
			start = text.find("$$")
			if start < 0:
				break
			m = re.compile(r"[^\s;,)]+").match(text, start + 2)
			if m is None:
				raise Exception(text)
			end = m.end()
			name = m.group()
			text = text[:start] + str(self.patcher.consts[name]) + text[end:]
		return text

	def process_macro(self, text: str) -> str:
		name, *rest = text.split(None, 1)
		if rest:
			args = rest[0]
		else:
			args = ""
		handler = MACRO_TABLE.get(name)
		if not handler:
			raise Exception(f"unrecognized macro: {name}")
		return handler(self, args)

	def next_label(self) -> str:
		assert(self.label_count != None)
		result = self.label_count
		self.label_count += 1
		return f"@label(auto_{result})"

	def next_ra(self) -> str:
		assert(self.ra_count != None)
		result = self.ra_count
		self.ra_count += 1
		return f"@ra(auto_{result})"

	@macro()
	def Msb(self, args: str) -> str:
		assert(self.name)
		script = self.name.removesuffix(".scs")
		language, index, text = args.split(":", 2)
		language = int(language, 10)
		index = int(index, 10)
		self.patcher.add_mst_line(script, language, index, text)
		return ""

	@macro()
	def CallFar(self, args: str) -> str:
		buffer, label = (x.strip() for x in args.split(","))
		ra = self.next_ra()
		return f"""
	CallFarRL {buffer}, {label}, {ra}
*{ra}:
"""

	@macro()
	def NvlMode(self, args: str) -> str:
		return f"""
	/CallFar 6, 245
	$W(4362) = 136;
"""

	@macro()
	def AdvMode(self, args: str) -> str:
		return f"""
	/CallFar 6, 246
	$W(4362) = 0;
"""

	@macro()
	def SemitransparentNvlMode(self, args: str) -> str:
		return f"""
	/CallFar 6, 245
	$W(4362) = 128;
"""

	@macro()
	def MesCls(self, args: str) -> str:
		return f"""
	MesCls_08 0
"""

	@macro()
	def MesMsbRA(self, args: str) -> str:
		ra, vid, mes_id = [x.strip() for x in args.split(",")]
		return f"""
	MesSetSavePointRL {ra}
	MessWindowOpen
	MessWindowOpenedWait
	MesVoiceWait
	MesSetMesMsb {vid}, {mes_id}
	MesMain
"""
	
	@macro()
	def MesScxRA(self, args: str) -> str:
		ra, vid, mes_id = [x.strip() for x in args.split(",")]
		return f"""
	MesSetSavePointRL {ra}
	MessWindowOpen
	MessWindowOpenedWait
	MesVoiceWait
	MesSetMesScx {vid}, {mes_id}
	MesMain
"""
		
	@macro()
	def MesMsb(self, args: str) -> str:
		vid, mes_id = [x.strip() for x in args.split(",")]
		ra = self.next_ra()
		return f"""
*{ra}:
	/MesMsbRA {ra}, {vid}, {mes_id}
"""

	@macro()
	def MesScx(self, args: str) -> str:
		vid, mes_id = [x.strip() for x in args.split(",")]
		return f"""
	MesSetSavePoint
	MessWindowOpen
	MessWindowOpenedWait
	MesVoiceWait
	MesSetMesScx {vid}, {mes_id}
	MesMain
"""

	@macro()
	def Mes2VMsbRA(self, args: str) -> str:
		ra, voice, anim, vid, mes_id = [x.strip() for x in args.split(",")]
		return f"""
	MesSetSavePointRL {ra}
	MessWindowOpen
	MessWindowOpenedWait
	MesVoiceWait
	Mes2VSetMesMsb {voice}, {anim}, {vid}, {mes_id}
	MesMain
"""

	@macro()
	def Mes2VMsb(self, args: str) -> str:
		voice, anim, vid, mes_id = [x.strip() for x in args.split(",")]
		ra = self.next_ra()
		return f"""
*{ra}:
	/Mes2VMsbRA {ra}, {voice}, {anim}, {vid}, {mes_id}
"""

	@macro()
	def MesSync(self, args: str) -> str:
		return f"""
	MesSync_00
	MesSync_01
	MesSync_02
	MesSync_03
	MesSync_04
"""

	@macro()
	def MesSMsbRA(self, args: str) -> str:
		ra, window, vid, mes_id = [x.strip() for x in args.split(",")]
		return f"""
	MesSSetSavePointRL {ra}, {window}
	MesVoiceWait
	MesSSetMesMsb {vid}, {mes_id}
"""

	@macro()
	def MesSMsb(self, args: str) -> str:
		window, vid, mes_id = [x.strip() for x in args.split(",")]
		ra = self.next_ra()
		return f"""
*{ra}:
	/MesSMsbRA {ra}, {window}, {vid}, {mes_id}
"""

	@macro()
	def MesS2VMsbRA(self, args: str) -> str:
		ra, window, voice, anim, vid, mes_id = [x.strip() for x in args.split(",")]
		return f"""
	MesSSetSavePointRL {ra}, {window}
	MesVoiceWait
	MesS2VSetMesMsb {voice}, {anim}, {vid}, {mes_id}
"""

	@macro()
	def MesS2VMsb(self, args: str) -> str:
		window, voice, anim, vid, mes_id = [x.strip() for x in args.split(",")]
		ra = self.next_ra()
		return f"""
*{ra}:
	/MesS2VMsbRA {ra}, {window}, {voice}, {anim}, {vid}, {mes_id}
"""

	@macro()
	def InitMesSync1(self, args: str) -> str:
		return f"""
	MessWindowFastClose 1
	$W(4373) = 1;
	$W(4372) = 136;
	MessWindowOpenEx 1
	MessWindowOpenedWait
"""

	@macro()
	def ResetMesSync1(self, args: str) -> str:
		return f"""
	MessWindowFastClose 1
"""

	@macro()
	def CloseMesSync1(self, args: str) -> str:
		return f"""
	MessWindowCloseEx 1
	MessWindowClosedWait
"""

	@macro()
	def Mes(self, args: str) -> str:
		vid, mes = [x.strip() for x in args.split(",")]
		mes_id = mes.split(":", 1)[0]
		return f"""
	/Msb 00:{mes}
	/MesMsb {vid}, {mes_id}
"""

	@macro()
	def Mes2V(self, args: str) -> str:
		voice, anim, vid, mes = [x.strip() for x in args.split(",")]
		mes_id = mes.split(":", 1)[0]
		return f"""
	/Msb 00:{mes}
	/Mes2VMsb {voice}, {anim}, {vid}, {mes_id}
"""

	@macro()
	def SetRevMes(self, args: str) -> str:
		mes, = [x.strip() for x in args.split(",")]
		mes_id = mes.split(":", 1)[0]
		return f"""
	/Msb 00:{mes}
	SetRevMesMsb {mes_id}
"""

	@macro()
	def SetRevMesV(self, args: str) -> str:
		voice, vid, mes = [x.strip() for x in args.split(",")]
		mes_id = mes.split(":", 1)[0]
		return f"""
	/Msb 00:{mes}
	SetRevMesVMsb {voice}, {vid}, {mes_id}
"""

	@macro()
	def CenterLog1(self, args: str) -> str:
		mes_1, time = [x.strip() for x in args.split(",")]
		time = int(time) * 3 // 50
		mes_1_id, mes_1_text = mes_1.split(":", 1)
		return f"""
	/Mes 0, {mes_1_id}:\\lf:$$cl1;\\lc;{mes_1_text}\\a:{time};
	/MesCls
"""

	@macro()
	def CenterLog2(self, args: str) -> str:
		mes_1, mes_2, time = [x.strip() for x in args.split(",")]
		time = int(time) * 3 // 50
		mes_1_id, mes_1_text = mes_1.split(":", 1)
		mes_2_id, mes_2_text = mes_2.split(":", 1)
		return f"""
	/Mes 0, {mes_1_id}:\\lf:$$cl2;\\lc;{mes_1_text}\\a:{time};
	/Mes 0, {mes_2_id}:\\lc;{mes_2_text}\\a:{time};
	/MesCls
"""

	@macro()
	def CenterLog3(self, args: str) -> str:
		mes_1, mes_2, mes_3, time = [x.strip() for x in args.split(",")]
		time = int(time) * 3 // 50
		mes_1_id, mes_1_text = mes_1.split(":", 1)
		mes_2_id, mes_2_text = mes_2.split(":", 1)
		mes_3_id, mes_3_text = mes_3.split(":", 1)
		return f"""
	/Mes 0, {mes_1_id}:\\lf:$$cl3;\\lc;{mes_1_text}\\a:{time};
	/Mes 0, {mes_2_id}:\\lc;{mes_2_text}\\a:{time};
	/Mes 0, {mes_3_id}:\\lc;{mes_3_text}\\a:{time};
	/MesCls
"""

	@macro()
	def DeleteAll(self, args: str) -> str:
		return f"""
	$W(10 * 1 + 4401) = 255;
	$W(1 * 1 + 2786) = 0;
	$T(47) = 65280;
	/CallFar 6, 100
	$T(47) = 255;
	/CallFar 6, 4
"""

	@macro()
	def MessWindowCloseWait(self, args: str) -> str:
		return f"""
	MessWindowCloseEx 0
	MessWindowClosedWait
"""

	@macro()
	def Wait(self, args: str) -> str:
		time, = [x.strip() for x in args.split(",")]
		return f"""
	Mwait ({time}) * 3 / 50, 0
"""

	@macro()
	def MesWaitKey(self, args: str) -> str:
		return f"""
	/CallFar 7, 153
"""

	@macro()
	def ReleaseBg(self, args: str) -> str:
		buf, = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = 1 << ({buf});
	/CallFar 6, 4
"""

	@macro()
	def LoadBgAlpha(self, args: str) -> str:
		buf, bg, pri, x, y, alpha = [x.strip() for x in args.split(",")]
		self.next_label()
		return f"""
	/ReleaseBg {buf}
	BGload 1 << ({buf}), {bg}
	$W(({buf}) * 40 + 4500) = ({x}) * -1;
	$W(({buf}) * 40 + 4501) = ({y}) * -1;
	$W(({buf}) * 40 + 4508) = ({pri});
	$T(54) = ({bg});
	/CallFar 7, 39
	$W(({buf}) * 40 + 4513) = {alpha} * 255 / 1000;
	SetFlag 2400 + ({buf})
"""

	@macro()
	def LoadBg(self, args: str) -> str:
		buf, bg, pri, x, y = [x.strip() for x in args.split(",")]
		return f"""
	/LoadBgAlpha {buf}, {bg}, {pri}, {x}, {y}, 0
"""

	@macro()
	def LoadBgOnTop(self, args: str) -> str:
		back, front, bg, pri, x, y = [x.strip() for x in args.split(",")]
		return f"""
	$W(({back}) * 40 + 4508) = ({pri});
	/LoadBg {front}, {bg}, ({pri})+1, {x}, {y}
"""

	@macro()
	def AsyncFadeBg(self, args: str) -> str:
		job, buf, time, alpha = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = ({job});
	$T(48) = ({alpha}) * 255 / 1000;
	$T(49) = ({time}) * 3 / 50;
	$T(50) = ({buf}) * 40 + 4513;
	$T(51) = ({buf}) * 10 + 2408;
	SetFlag 10 + ({job})
	CreateThread 6, 6, 1698
"""

	@macro()
	def FadeBg(self, args: str) -> str:
		buf, time, alpha = [x.strip() for x in args.split(",")]
		_loop = self.next_label()
		_loop_end = self.next_label()
		return f"""
	If ({time}) * 3 / 50 <= 0, {_loop_end}
	$T(63) = ({alpha}) * 255 / 1000 - $W(({buf}) * 40 + 4513);
	$T(64) = 0;
{_loop}:
	$T(64) += 1;
	CalcMove ({buf}) * 10 + 2408, $T(63), $T(64), ({time}) * 3 / 50
	Mwait 1, 0
	If $T(64) <= ({time}) * 3 / 50, {_loop}
{_loop_end}:
	$W(({buf}) * 40 + 4513) = ({alpha}) * 255 / 1000;
	$W(({buf}) * 10 + 2408) = 0;
"""

	@macro()
	def AsyncMoveBg(self, args: str) -> str:
		job, buffer, time, x, y = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = ({job});
	$T(48) = $W(({buffer}) * 40 + 4500) + ({x}) * -1;
	$T(49) = $W(({buffer}) * 40 + 4501) + ({y}) * -1;
	$T(50) = ({time}) * 3 / 50;
	$T(51) = ({buffer}) * 40 + 4500;
	$T(52) = ({buffer}) * 40 + 4501;
	$T(53) = ({buffer}) * 10 + 2400;
	$T(54) = ({buffer}) * 10 + 2401;
	SetFlag 10 + ({job})
	CreateThread 6, 6, 1704
"""

	@macro()
	def MoveBg(self, args: str) -> str:
		buf, time, x, y = [x.strip() for x in args.split(",")]
		_loop = self.next_label()
		_loop_end = self.next_label()
		return f"""
	If ({time}) <= 0, {_loop_end}
	$T(62) = ({x}) * -1 - $W(({buf}) * 40 + 4500);
	$T(63) = ({y}) * -1 - $W(({buf}) * 40 + 4501);
	$T(64) = 0;
{_loop}:
	$T(64) += 1;
	CalcMove ({buf}) * 10 + 2400, $T(62), $T(64), ({time}) * 3 / 50
	CalcMove ({buf}) * 10 + 2401, $T(63), $T(64), ({time}) * 3 / 50
	Mwait 1, 0
	If $T(64) <= ({time}) * 3 / 50, {_loop}
{_loop_end}:
	$W(({buf}) * 40 + 4500) = ({x}) * -1;
	$W(({buf}) * 40 + 4501) = ({y}) * -1;
	$W(({buf}) * 10 + 2400) = 0;
	$W(({buf}) * 10 + 2401) = 0;
"""

	@macro()
	def MoveBgNowait(self, args: str) -> str:
		buf, time, x, y = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = ({buf});
	$W(1300 + ({buf})) = $W(({buf}) * 40 + 4500) + ({x}) * -1;
	$W(1318 + ({buf})) = $W(({buf}) * 40 + 4501) + ({y}) * -1;
	$W(1374 + ({buf})) = ({time}) * 3 / 50;
	/CallFarRL 6, 1547
"""

	@macro()
	def SwapBg(self, args: str) -> str:
		back, front = [x.strip() for x in args.split(",")]
		return f"""
	BGswap 1 << ({back}), 1 << ({front})
	$W(({back}) * 40 + 4508) = $W(({front}) * 40 + 4508);
	$T(47) = 1 << ({front});
	/CallFar 6, 4
"""

	@macro()
	def TransitionBg(self, args: str) -> str:
		buf, time, data = [x.strip() for x in args.split(",")]
		return f"""
	LoadPic 100 + 15, 5, {data}
	$W(6370 + 15) = ({data});
	$W(({buf}) * 40 + 4513) = 255;
	$T(76) = 0 * (255 + 32) / 100;
	$T(77) = 100 * (255 + 32) / 100;
	$W(({buf}) * 40 + 4514) = 15;
	$W(({buf}) * 40 + 4515) = 32;
	$W(({buf}) * 40 + 4511) = 16;
	$W(({buf}) * 40 + 4510) = $T(76);

	$T(47) = 8;
	$T(48) = $T(77);
	$T(49) = ({time}) * 3 / 50;
	$T(50) = ({buf}) * 40 + 4510;
	SetFlag 18
	CreateThread 6, 6, 1701
	FlagOnWait 19 + 8

"""

	@macro()
	def CrossfadeBg(self, args: str) -> str:
		back, front, time = [x.strip() for x in args.split(",")]
		return f"""
	/FadeBg {front}, {time}, 1000
	/SwapBg {back}, {front}
"""

	@macro()
	def AsyncShakeBg(self, args: str) -> str:
		job, buf, time, start_x, start_y, end_x, end_y, freq = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = ({job});
	$T(48) = ({buf});
	$T(49) = ({start_x});
	$T(50) = ({start_y});
	$T(51) = ({end_x});
	$T(52) = ({end_y});
	$T(53) = ({freq});
	$T(54) = ({time});
	SetFlag 10 + ({job})
	CreateThread 6, 7, 88
"""

	@macro()
	def ClearAll(self, args: str) -> str:
		time = args.strip()
		return f"""
	/StopSe {time}
	/StopSe2 {time}
	/StopSe3 {time}
	/StopBgm {time}
	/CallFar 7, 6
	/MessWindowCloseWait
	$W(1022) = ({time}) * 3 / 50;
	/CallFar 6, 812
	/EndMovie
	$W(0 * 20 + 6002) = 0;
	$W(0 * 20 + 6004) = 49152;
	$W(0 * 20 + 6008) = 0;
	$W(0 * 20 + 6006) = 0;
	$W(0 * 20 + 6003) = 255;
	$W(0 * 20 + 6005) = 65535;
	$W(0 * 20 + 6007) = 2000;
	$W(0 * 20 + 6009) = 3000;
	$W(0 * 20 + 6010) = 1;
	$W(0 * 20 + 6011) = 13;
	$W(0 * 20 + 6012) = 3000;
	$W(0 * 20 + 6000) = 16777215;
	$W(0 * 20 + 6001) = 16777215;
	$W(0 * 20 + 6017) = 65535;
	$W(0 * 20 + 6018) = 65535;
	$W(0 * 20 + 6019) = 0;
	$W(1 * 20 + 6002) = 0;
	$W(1 * 20 + 6004) = 49152;
	$W(1 * 20 + 6008) = 0;
	$W(1 * 20 + 6006) = 0;
	$W(1 * 20 + 6003) = 255;
	$W(1 * 20 + 6005) = 65535;
	$W(1 * 20 + 6007) = 2000;
	$W(1 * 20 + 6009) = 3000;
	$W(1 * 20 + 6010) = 1;
	$W(1 * 20 + 6011) = 13;
	$W(1 * 20 + 6012) = 3000;
	$W(1 * 20 + 6000) = 16777215;
	$W(1 * 20 + 6001) = 16777215;
	$W(1 * 20 + 6017) = 65535;
	$W(1 * 20 + 6018) = 65535;
	$W(1 * 20 + 6019) = 0;
	ThreadControl 7, 0
	ResetFlag 449
	FlagOnWait 453
	$W(1260) = 0;
	$W(1260) = 0;
	ThreadControl 6, 0
	/CallFar 6, 47
	/CallFar 6, 49
	/CallFar 6, 845
	/CallFar 7, 1
	/CallFar 7, 7
"""

	@macro()
	def IntermissionIn(self, args: str) -> str:
		_7 = self.next_label()
		_9 = self.next_label()
		return f"""
	$W(4400 + 10 * 1 + 0) = 0;
	$W(4400 + 10 * 1 + 1) = 0;
	$W(4400 + 10 * 1 + 2) = 99;
	$W(4400 + 10 * 1 + 3) = 0;
	$W(4400 + 10 * 1 + 4) = 0;
	$W(4400 + 10 * 1 + 5) = 0;
	$W(4400 + 10 * 1 + 6) = 0;
	$W(2786 + 1 * 1 + 0) = 0;
	$W(4400 + 10 * 1 + 0) = 0;
	$W(4400 + 10 * 1 + 1) = 0;
	$W(4400 + 10 * 1 + 2) = 90;
	/PlayMovieMask 49, 91, 1000
	/WaitMovie
"""

	@macro()
	def IntermissionIn2(self, args: str) -> str:
		_16 = self.next_label()
		_18 = self.next_label()
		return f"""
	/Wait 500
	/PlayMovieMask 50, 91, 1000
	/Wait 300
	$W(4400 + 10 * 1 + 0) = 0;
	$W(4400 + 10 * 1 + 1) = 0;
	$W(4400 + 10 * 1 + 2) = 99;
	$W(4400 + 10 * 1 + 3) = 0;
	$W(4400 + 10 * 1 + 4) = 0;
	$W(4400 + 10 * 1 + 5) = 0;
	$W(4400 + 10 * 1 + 6) = 0;
	$W(2786 + 1 * 1 + 0) = 0;
	/WaitMovie
"""

	@macro()
	def PlayMovie(self, args: str) -> str:
		index, pri, alpha = [x.strip() for x in args.split(",")]
		return f"""
	SetFlag 2488
	$W(6338) = 0;
	$W(6330) = ({pri});
	PlayMovie {index}, 0
	FlagOnWait 1236
	$W(6338) = ({alpha}) * 255 / 1000;
"""

	@macro()
	def PlayMovieLoop(self, args: str) -> str:
		index, pri, alpha = [x.strip() for x in args.split(",")]
		return f"""
	SetFlag 2488
	$W(6338) = 0;
	$W(6330) = ({pri});
	PlayMovieLoop {index}, 0
	FlagOnWait 1236
	$W(6338) = ({alpha}) * 255 / 1000;
"""

	@macro()
	def PlayMovieMask(self, args: str) -> str:
		index, pri, alpha = [x.strip() for x in args.split(",")]
		return f"""
	SetFlag 2488
	$W(6338) = 0;
	$W(6330) = ({pri});
	PlayMovieMask {index}, 0
	FlagOnWait 1236
	$W(6338) = ({alpha}) * 255 / 1000;
"""

	@macro()
	def WaitMovie(self, args: str) -> str:
		_16 = self.next_label()
		_18 = self.next_label()
		return f"""
	FlagOffJump 1851, {_18}
{_16}:
	Wait 1
	KeyOnJump2 5, 1, {_18}
	KeyOnJump2 6, 1, {_18}
	FlagOnJump 1234, {_18}
	FlagOffJump 1851, {_18}
	Jump {_16}
{_18}:
	/EndMovie
"""

	@macro()
	def EndMovie(self, args: str) -> str:
		return f"""
	EndMovie
	$W(6338) = 0;
	$W(6330) = 65535;
	ResetFlag 2488
"""

	@macro()
	def AsyncFadeMovie(self, args: str) -> str:
		job, time, alpha = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = ({job});
	$T(48) = ({alpha}) * 255 / 1000;
	$T(49) = ({time}) * 3 / 50;
	$T(50) = 6338;
	SetFlag 10 + ({job})
	CreateThread 6, 6, 1701
"""

	@macro()
	def FadeMovie(self, args: str) -> str:
		time, alpha = [x.strip() for x in args.split(",")]
		_loop = self.next_label()
		_loop_end = self.next_label()
		return f"""
	If ({time}) <= 0, {_loop_end}
	$T(63) = ({alpha}) * 255 / 1000 - $W(6338);
	$T(64) = 0;
{_loop}:
	$T(64) += 1;
	CalcMove 6338, $T(63), $T(64), ({time}) * 3 / 50
	Mwait 1, 0
	If $T(64) <= ({time}) * 3 / 50, {_loop}
{_loop_end}:
	$W(6338) = ({alpha}) * 255 / 1000;
"""

	@macro()
	def WaitVoice(self, args: str) -> str:
		_loop = self.next_label()
		_loop_end = self.next_label()
		return f"""
{_loop}:
	FlagOnJump 1234, {_loop_end}
	GetSystemStatus 1
	If $T(7), {_loop_end}
	Wait 1
	Jump {_loop}
{_loop_end}:
"""

	@macro()
	def PlaySe(self, args: str) -> str:
		index, fade, volume, loop = [x.strip() for x in args.split(",")]
		_58 = self.next_label()
		return f"""
	FlagOnJump 2824, {_58}
	/CallFar 6, 55
	/SetSeVolume {volume}
	$W(2191) = ({fade}) * 3 / 50;
	SEplay {index}, {loop}
	/CallFar 6, 1049
{_58}:
"""

	@macro()
	def WaitSe(self, args: str) -> str:
		_loop = self.next_label()
		_loop_end = self.next_label()
		return f"""
{_loop}:
	FlagOnJump 1234, {_loop_end}
	GetSystemStatus 3
	If $T(7), {_loop_end}
	Wait 1
	Jump {_loop}
{_loop_end}:
"""

	@macro()
	def SetSeVolume(self, args: str) -> str:
		volume, = [x.strip() for x in args.split(",")]
		return f"""
	$W(4315) = ({volume}) / 10;
"""

	@macro()
	def StopSe(self, args: str) -> str:
		fade, = [x.strip() for x in args.split(",")]
		return f"""
	$W(2191) = ({fade}) * 3 / 50;
	SEstop
"""

	@macro()
	def PlaySe2(self, args: str) -> str:
		index, fade, volume, loop = [x.strip() for x in args.split(",")]
		_58 = self.next_label()
		return f"""
	FlagOnJump 2824, {_58}
	/CallFar 6, 56
	/SetSe2Volume {volume}
	$W(2191) = ({fade}) * 3 / 50;
	SEplay2 {index}, {loop}
	/CallFar 6, 1054
{_58}:
"""

	@macro()
	def WaitSe2(self, args: str) -> str:
		_loop = self.next_label()
		_loop_end = self.next_label()
		return f"""
{_loop}:
	FlagOnJump 1234, {_loop_end}
	GetSystemStatus 4
	If $T(7), {_loop_end}
	Wait 1
	Jump {_loop}
{_loop_end}:
"""

	@macro()
	def SetSe2Volume(self, args: str) -> str:
		volume, = [x.strip() for x in args.split(",")]
		return f"""
	$W(4316) = ({volume}) / 10;
"""

	@macro()
	def StopSe2(self, args: str) -> str:
		fade, = [x.strip() for x in args.split(",")]
		return f"""
	$W(2191) = ({fade}) * 3 / 50;
	SEstop2
"""

	@macro()
	def PlaySe3(self, args: str) -> str:
		index, fade, volume, loop = [x.strip() for x in args.split(",")]
		_58 = self.next_label()
		return f"""
	FlagOnJump 2824, {_58}
	/CallFar 6, 57
	/SetSe3Volume {volume}
	$W(2191) = ({fade}) * 3 / 50;
	SEplay3 {index}, {loop}
	/CallFar 6, 1068
{_58}:
"""

	@macro()
	def WaitSe3(self, args: str) -> str:
		_loop = self.next_label()
		_loop_end = self.next_label()
		return f"""
{_loop}:
	FlagOnJump 1234, {_loop_end}
	GetSystemStatus 5
	If $T(7), {_loop_end}
	Wait 1
	Jump {_loop}
{_loop_end}:
"""

	@macro()
	def SetSe3Volume(self, args: str) -> str:
		volume, = [x.strip() for x in args.split(",")]
		return f"""
	$W(4317) = ({volume}) / 10;
"""

	@macro()
	def StopSe3(self, args: str) -> str:
		fade, = [x.strip() for x in args.split(",")]
		return f"""
	$W(2191) = ({fade}) * 3 / 50;
	SEstop3
"""

	@macro()
	def StopBgm(self, args: str) -> str:
		fade, = [x.strip() for x in args.split(",")]
		return f"""
	$W(2190) = ({fade}) * 3 / 50;
	BGMstop
"""

	@macro()
	def ReleaseCha(self, args: str) -> str:
		buf, = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = 256 << ({buf}) | 256 << ({buf}) + 4;
	/CallFar 6, 100
"""

	@macro()
	def LoadCha(self, args: str) -> str:
		buf, cha, pri, x = [x.strip() for x in args.split(",")]
		no_hazuki_glasses = self.next_label()
		after = self.next_label()
		return f"""
	$W(({buf}) * 40 + 5110) = ({pri});
	$T(47) = 256 << ({buf}) + 4;
	/CallFar 6, 100
	If ({cha}) & 65535 < 692, {no_hazuki_glasses}
	If 707 < ({cha}) & 65535, {no_hazuki_glasses}
	FlagOnJump 4008, {no_hazuki_glasses}
	CHAloadAtlas 1 << ({buf}) + 4, ({cha}) + 2
	CharaLayerLoad
	Jump {after}
{no_hazuki_glasses}:
	CHAloadAtlas 1 << ({buf}) + 4, {cha}
	CharaLayerLoad
{after}:
	$W((({buf}) + 4) * 40 + 5100) = 640 + ({x});
	$W((({buf}) + 4) * 40 + 5101) = 420;
"""

	@macro()
	def LoadChaAlpha(self, args: str) -> str:
		buf, cha, pri, x, alpha = [x.strip() for x in args.split(",")]
		return f"""
	/LoadCha {buf}, {cha}, {pri}, {x}
	$W((({buf}) + 4) * 40 + 5107) = ({alpha}) * 255 / 1000;
"""

	@macro()
	def AsyncFadeCha(self, args: str) -> str:
		job, buf, time, alpha = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = ({job});
	$T(48) = ({alpha}) * 255 / 1000;
	$T(49) = ({time}) * 3 / 50;
	$T(50) = ({buf}) * 40 + 5107;
	$T(51) = ({buf}) * 10 + 2507;
	SetFlag 10 + ({job})
	CreateThread 6, 6, 1698
"""

	@macro()
	def FadeCha(self, args: str) -> str:
		buf, time, alpha = [x.strip() for x in args.split(",")]
		_loop = self.next_label()
		_loop_end = self.next_label()
		return f"""
	If ({time}) <= 0, {_loop_end}
	$T(63) = ({alpha}) * 255 / 1000 - $W(({buf}) * 40 + 5107);
	$T(64) = 0;
{_loop}:
	$T(64) += 1;
	CalcMove ({buf}) * 10 + 2507, $T(63), $T(64), ({time}) * 3 / 50
	Mwait 1, 0
	If $T(64) <= ({time}) * 3 / 50, {_loop}
{_loop_end}:
	$W(({buf}) * 40 + 5107) = ({alpha}) * 255 / 1000;
	$W(({buf}) * 10 + 2507) = 0;
"""

	@macro()
	def InCha(self, args: str) -> str:
		buf, time = [x.strip() for x in args.split(",")]
		return f"""
	$W(1022) = ({time}) * 3 / 50;
	SetFlag 0
	$W(51) = 4096 << ({buf});
	/CallFar 6, 343
"""

	@macro()
	def OutCha(self, args: str) -> str:
		buf, time = [x.strip() for x in args.split(",")]
		return f"""
	ResetFlag 0
	$W(51) = 256 << ({buf});
	$W(1022) = ({time}) * 3 / 50;
	/CallFar 6, 351
"""

	@macro()
	def AsyncMoveCha(self, args: str) -> str:
		job, buf, time, x, y = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = ({job});
	$T(48) = $W(({buf}) * 40 + 5100) + ({x});
	$T(49) = $W(({buf}) * 40 + 5101) + ({y});
	$T(50) = ({time}) * 3 / 50;
	$T(51) = ({buf}) * 40 + 5100;
	$T(52) = ({buf}) * 40 + 5101;
	$T(53) = ({buf}) * 10 + 2500;
	$T(54) = ({buf}) * 10 + 2501;
	SetFlag 10 + ({job})
	CreateThread 6, 6, 1704
"""

	@macro()
	def MoveCha(self, args: str) -> str:
		buf, time, x, y = [x.strip() for x in args.split(",")]
		_loop = self.next_label()
		_loop_end = self.next_label()
		return f"""
	If ({time}) <= 0, {_loop_end}
	$T(64) = 0;
{_loop}:
	$T(64) += 1;
	CalcMove ({buf}) * 10 + 2500, ({x}), $T(64), ({time}) * 3 / 50
	CalcMove ({buf}) * 10 + 2501, ({y}), $T(64), ({time}) * 3 / 50
	Mwait 1, 0
	If $T(64) <= ({time}) * 3 / 50, {_loop}
{_loop_end}:
	$W(({buf}) * 40 + 5100) = $W(({buf}) * 40 + 5100) + ({x});
	$W(({buf}) * 40 + 5101) = $W(({buf}) * 40 + 5101) + ({y});
	$W(({buf}) * 10 + 2500) = 0;
	$W(({buf}) * 10 + 2501) = 0;
"""

	@macro()
	def AsyncShakeCha(self, args: str) -> str:
		job, buf, time, start_x, start_y, end_x, end_y, freq = [x.strip() for x in args.split(",")]
		return f"""
	$T(47) = ({job});
	$T(48) = ({buf});
	$T(49) = ({start_x});
	$T(50) = ({start_y});
	$T(51) = ({end_x});
	$T(52) = ({end_y});
	$T(53) = ({freq});
	$T(54) = ({time});
	SetFlag 10 + ({job})
	CreateThread 6, 7, 95
"""

	@macro()
	def Await(self, args: str) -> str:
		job = args.strip()
		return f"""
	FlagOnWait 19 + ({job})
"""
