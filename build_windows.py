import glob
import json
import os
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Union

from lib.config import WINDOWS_RESOURCES_PATH
from lib.ScriptPatcher import ScriptPatcher
from lib.TranslationProcessor import TranslationProcessor
from lib.utils import (
	run_command,
	run_command_silent,
	load_text,
	load_lines,
	load_cls,
	load_yaml,
	clean_tree,
	pack_cpk,
	unpack_cpk,
	compile_scripts,
	decompile_scripts,
)

flag_set = "chaos_head_windows"

data_dir = Path("data")
build_dir = Path("build/windows")
out_dir = Path("out/windows")

src_dir = build_dir / "src"
dst_dir = build_dir / "dst"

src_script_dir = src_dir / "script"
raw_scs_dir = build_dir / "scs"
patch_scs_dir = build_dir / "scs-patched"
dst_script_dir = dst_dir / "script"

def load_custom_cls(name: str) -> dict[int, str]:
	return load_cls(data_dir / f"cls_win/{name}.cls")

def unpack_archive(dst_dir: Path, arc_name: str) -> None:
	cpk_path = WINDOWS_RESOURCES_PATH / f"{arc_name}.cpk"
	entries = load_custom_cls(arc_name)
	if os.path.exists(dst_dir):
		#print(f"{dst_dir} already exists, skipping")
		return
	unpack_cpk(dst_dir, cpk_path, entries)

def repack_archive(arc_name: str, src_dir: Path) -> None:
	cpk_path = out_dir / f"c0{arc_name}.cpk"
	entries = load_custom_cls(arc_name)
	pack_cpk(cpk_path, src_dir, entries)

unpack_archive(src_script_dir, "script")
unpack_archive(src_script_dir / "mes00", "mes00")
unpack_archive(src_script_dir / "mes01", "mes01")

constants = load_yaml(data_dir / "consts.yaml")

for arc_name in ["bg", "bgm", "mask", "movie", "script", "se", "voice"]:
	for index, name in load_custom_cls(arc_name).items():
		constants[name.split(".", 1)[0]] = index

if not raw_scs_dir.exists():
	decompile_scripts(raw_scs_dir, src_script_dir, flag_set)
with open(raw_scs_dir / "schzdoz_223.scs", "w", encoding="utf-8") as f:
	f.write("0:\n")
with open(raw_scs_dir / "schzdoz_223.sct", "w", encoding="utf-8") as f:
	pass
with open(raw_scs_dir / "mes01" / "schzdoz_223_01.mst", "w", encoding="utf-8") as f:
	f.write("0:\n")
shutil.copytree(raw_scs_dir, patch_scs_dir, dirs_exist_ok=True)

patcher = ScriptPatcher(patch_scs_dir, build_dir, constants)
def load_patches(root: Path) -> None:
	for name in glob.glob("**/*.patch", root_dir=root, recursive=True):
		print(root,"\\",name, sep='')
		text = load_text(root / name)
		patcher.add_patch(name, text)
load_patches(data_dir / "patches_common")
load_patches(data_dir / "patches_win")
txt_dir = data_dir / "txt_eng"
TranslationProcessor(patcher, "10_translation/", txt_dir, True).run()
patcher.run()

compile_scripts(dst_script_dir, patch_scs_dir, flag_set)

out_dir.mkdir(parents=True, exist_ok=True)
repack_archive("script", dst_script_dir)
repack_archive("mes00", dst_script_dir / "mes00")
repack_archive("mes01", dst_script_dir / "mes01")
