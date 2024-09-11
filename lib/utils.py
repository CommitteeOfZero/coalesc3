import array
import os
from pathlib import Path
import shutil
import subprocess
import wave
import yaml

from lib.config import (
	MGSSCRIPTTOOLS_PATH,

	BANK_PATH,
)
from lib.cri.cpk.writer import (
	Config as CpkConfig,
	Writer as CpkWriter,
)
from lib.cri.cpk.reader import Reader as CpkReader

def clean_tree(path: str) -> None:
	if os.path.exists(path):
		shutil.rmtree(path)

def run_command(*args: list[str]) -> None:
	subprocess.run(args, check=True)

def run_command_silent(*args: list[str]) -> None:
	process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if process.returncode != 0:
		print(process.stdout.decode("utf-8", errors="replace"), end="")
		print(process.stderr.decode("utf-8", errors="replace"), end="")
	process.check_returncode()

def save_text(path: str, text: str) -> None:
	with open(path, "w", encoding="utf-8") as f:
		f.write(text)

def load_text(path: str) -> str:
	with open(path, encoding="utf-8-sig") as f:
		return f.read()

def save_lines(path: str, lines: list[str]) -> None:
	text = "".join(f"{line}\n" for line in lines)
	save_text(path, text)

def load_lines(path: str) -> list[str]:
	return load_text(path).splitlines()

def load_cls(path: str) -> dict[int, str]:
	names = load_lines(path)
	return {index: name for index, name in enumerate(names)}

def save_mst(path: str, entries: dict[int, str]) -> None:
	lines = (
		f"{index}:{entries[index]}"
		for index in sorted(entries.keys())
	)
	save_lines(path, lines)

def load_mst(path: str) -> dict[int, str]:
	entries = {}
	for line in load_lines(path):
		index, entry = line.split(":", 1)
		index = int(index)
		if index in entries:
			raise Exception(f"Duplicate MES index: {index}")
		entries[index] = entry
	return entries

def load_yaml(path: str):
	return yaml.safe_load(load_text(path))

def pack_cpk(cpk_path: str, src_dir: Path, entries: dict[int, str]) -> None:
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

def unpack_cpk(dst_dir: Path, cpk_path: str, entries: dict[int, str]) -> None:
	with open(cpk_path, "rb") as cpk_fp:
		reader = CpkReader(cpk_fp)
		for entry in reader.entries:
			name = entries[entry.id_]
			with open(dst_dir / name, "wb") as file_fp:
				file_fp.write(reader.read_file(entry.index))

def compile_scripts(dst_dir: Path, src_dir: Path, flag_set: str) -> None:
	run_command(
		MGSSCRIPTTOOLS_PATH,
		"--mode", "Compile",
		"--bank-directory", BANK_PATH,
		"--flag-set", flag_set,
		# "--instruction-sets", "base,chaos_head_noah",
		"--charset", "chaos_head_noah-extended",
		# "--string-syntax", "ScsStrict",
		"--uncompiled-directory", src_dir,
		"--compiled-directory", dst_dir,
	)

def decompile_scripts(dst_dir: Path, src_dir: Path, flag_set: str) -> None:
	run_command(
		MGSSCRIPTTOOLS_PATH,
		"--mode", "Decompile",
		"--bank-directory", BANK_PATH,
		"--flag-set", flag_set,
		# "--instruction-sets", "base,chaos_head_noah",
		"--charset", "chaos_head_noah-extended",
		# "--string-syntax", "ScsStrict",
		"--uncompiled-directory", dst_dir,
		"--compiled-directory", src_dir,
	)

