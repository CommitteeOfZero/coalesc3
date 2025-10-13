import os
from pathlib import Path
import shutil
import subprocess
import yaml
import re

from typing import Callable, assert_never

from lib.config import (
	MGSSCRIPTTOOLS_PATH,
	UNGELIFY_PATH,
	BANK_PATH,
)
from lib.cri.cpk.writer import (
	Config as CpkConfig,
	Writer as CpkWriter,
)
from lib.cri.cpk.reader import Reader as CpkReader
from lib.types import BuildInfo, ArchiveFormat, ScriptFormat

def clean_tree(path: str) -> None:
	if os.path.exists(path):
		shutil.rmtree(path)

def run_command(*args: str | Path) -> None:
	subprocess.run(args, check=True)

def run_command_silent(args: list[str]) -> None:
	process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if process.returncode != 0:
		print(process.stdout.decode("utf-8", errors="replace"), end="")
		print(process.stderr.decode("utf-8", errors="replace"), end="")
	process.check_returncode()

def save_text(path: Path, text: str) -> None:
	with open(path, "w", encoding="utf-8") as f:
		f.write(text)

def load_text(path: Path) -> str:
	with open(path, encoding="utf-8-sig") as f:
		return f.read()

def save_lines(path: Path, lines: list[str]) -> None:
	text = "".join(f"{line}\n" for line in lines)
	save_text(path, text)

def load_lines(path: Path) -> list[str]:
	return load_text(path).splitlines()

def load_cls(path: Path) -> dict[int, str]:
	names = load_lines(path)
	return { index: name for index, name in enumerate(names) }

def save_mst(path: Path, entries: dict[int, str]) -> None:
	lines = [f"{index}:{entries[index]}" for index in sorted(entries.keys())]
	save_lines(path, lines)

def load_mst(path: Path, line_inc: int = 100, comments : list[str] = [], disable_italics : bool = False) -> dict[int, str]:
	entries : dict[int, str] = {}

	lines = load_lines(path)

	if disable_italics:
		for i in range(len(lines)):
			for instance in re.finditer(r"<i>(.*?)</i>", lines[i]):
				lines[i] = lines[i].replace(instance.group(), f"\\c:1;{ instance.groups()[0].replace("\\c:0;", "\\c:1;") }\\c:0;")

	lines = filter(lambda line : not any(line.startswith(tag) for tag in comments), lines)

	for num, line in enumerate(lines):
		if not re.match(r"^[0-9]+:", line): index, entry = num * line_inc, line
		else: index, entry = line.split(":", 1)
		index = int(index)
		if index in entries:
			raise Exception(f"Duplicate MES index: {index}")
		entries[index] = entry
	return entries

def load_yaml(path: Path):
	return yaml.safe_load(load_text(path))

def pack_cpk(cpk_path: Path, src_dir: Path, entries: dict[int, str]) -> None:
	with open(cpk_path, "wb") as cpk_fp:
		writer = CpkWriter(
			cpk_fp,
			CpkConfig(
				alignment=2048,
				encrypt_tables=False,
				randomize_padding=False,
			),
		)
		for index, name in entries.items():
			with open(src_dir / name, "rb") as file_fp:
				writer.write_file(index, name, file_fp.read())
		writer.close()

def pack_mpk(mpk_path: Path, src_dir: Path, entries: dict[int, str]):
	run_command(
		UNGELIFY_PATH,
		"replace",
		mpk_path,
		*map(lambda fl: src_dir / fl, entries.values())
	)

def unpack_cpk(dst_dir: Path, cpk_path: Path, entries: dict[int, str]) -> None:
	dst_dir.mkdir(parents=True, exist_ok=True)
	with open(cpk_path, "rb") as cpk_fp:
		reader = CpkReader(cpk_fp)
		for entry in reader.entries:
			name = entries[entry.id_]
			with open(dst_dir / name, "wb") as file_fp:
				file_fp.write(reader.read_file(entry.index))

def unpack_mpk(dst_dir: Path, mpk_path: Path, entries: dict[int, str]) -> None:
	dst_dir.mkdir(parents=True, exist_ok=True)
	run_command(
		UNGELIFY_PATH,
		"extract",
		"-o", dst_dir,
		mpk_path,
		*entries.values()
	)

def compile_scripts(dst_dir: Path, src_dir: Path, flag_set: str, charset: str) -> None:
	run_command(
		MGSSCRIPTTOOLS_PATH,
		"--mode", "Compile",
		"--bank-directory", BANK_PATH,
		"--flag-set", flag_set,
		# "--instruction-sets", "base,chaos_head_noah",
		"--charset", charset,
		# "--string-syntax", "ScsStrict",
		"--uncompiled-directory", src_dir,
		"--compiled-directory", dst_dir,
	)

def decompile_scripts(dst_dir: Path, src_dir: Path, flag_set: str, charset: str) -> None:
	run_command(
		MGSSCRIPTTOOLS_PATH,
		"--mode", "Decompile",
		"--bank-directory", BANK_PATH,
		"--flag-set", flag_set,
		# "--instruction-sets", "base,chaos_head_noah",
		"--charset", charset,
		# "--string-syntax", "ScsStrict",
		"--uncompiled-directory", dst_dir,
		"--compiled-directory", src_dir,
	)

def get_custom_cls_loader(partial : Path) -> Callable[[str], dict[int, str]]:
	def inner(name: str) -> dict[int, str]:
		return load_cls(partial / f"{ name }.cls")
	return inner

def get_archive_unpacker(src_script_dir : Path, custom_cls_loader : Callable[[str], dict[int, str]], build_info : BuildInfo) -> Callable[[Path, str], None]:
	def inner(dst_dir: Path, arc_name: str) -> None:
		if os.path.exists(dst_dir) and not build_info.clean: return

		archive_path : Path = src_script_dir / f"{ arc_name }{ build_info.archive }"
		entries = custom_cls_loader(arc_name)

		match build_info.archive:
			case ArchiveFormat.MPK:
				unpack_mpk(dst_dir, archive_path, entries)
			case ArchiveFormat.CPK:
				unpack_cpk(dst_dir, archive_path, entries)
				if build_info.in_fmt != ScriptFormat.MST or arc_name != "script": return

				for lang in build_info.langs:
					unpack_cpk(dst_dir / f"mes{+lang:02}", src_script_dir / f"mes{+lang:02}.cpk", custom_cls_loader(f"mes{+lang:02}"))
			case None:
				assert False, "Unreachable"
			case _:
				assert_never(build_info.archive)
	return inner

def get_archive_repacker(src_script_dir : Path, out_dir : Path, custom_cls_loader : Callable[[str], dict[int, str]], build_info : BuildInfo) -> Callable[[str, Path], None]:
	def inner(arc_name: str, src_dir: Path) -> None:
		match build_info.archive:
			case ArchiveFormat.MPK:
				run_command("cp", src_script_dir / "script.mpk", out_dir / "enscript.mpk")
				pack_mpk(out_dir / f"enscript.mpk", src_dir, custom_cls_loader(arc_name))
			case ArchiveFormat.CPK:
				pack_cpk(out_dir / f"c0{ arc_name }.cpk", src_dir, custom_cls_loader(arc_name))
				if build_info.in_fmt != ScriptFormat.MST or arc_name != "script": return

				for lang in build_info.langs :
					pack_cpk(out_dir / f"mes{+lang:02}.cpk", src_dir / f"mes{+lang:02}", custom_cls_loader(f"mes{+lang:02}"))
			case None:
				assert False, "Unreachable"
			case _:
				assert_never(build_info.archive)
	return inner