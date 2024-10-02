import glob
import json
import os
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Union

from lib.config import SWITCH_JPN_RESOURCES_PATH
from lib.ScriptPatcher import ScriptPatcher
from lib.utils import (
	run_command,
	run_command_silent,
	load_text,
	load_lines,
	load_cls,
	load_yaml,
	clean_tree,
	compile_scripts,
	decompile_scripts,
)

flag_set = "chaos_head_switch"

data_dir = Path("data")
build_dir = Path("build/switch_jpn")
out_dir = Path("out/switch_jpn")

src_dir = build_dir / "src"
dst_dir = build_dir / "dst"

src_script_dir = SWITCH_JPN_RESOURCES_PATH / "script"
raw_scs_dir = build_dir / "scs"
patch_scs_dir = build_dir / "scs-patched"
dst_script_dir = dst_dir / "script"

def load_custom_cls(name: str) -> dict[int, str]:
	return load_cls(data_dir / f"cls_swi_jpn/{name}.cls")

constants = load_yaml(data_dir / "consts.yaml")

for arc_name in ["bg", "bgm", "mask", "movie", "script", "se", "voice"]:
	for index, name in load_custom_cls(arc_name).items():
		constants[name.split(".", 1)[0]] = index

if not raw_scs_dir.exists():
	decompile_scripts(raw_scs_dir, src_script_dir, flag_set)
shutil.copytree(raw_scs_dir, patch_scs_dir, dirs_exist_ok=True)

patcher = ScriptPatcher(patch_scs_dir, build_dir, constants)
def load_patches(root: Path) -> None:
	for name in glob.glob("**/*.patch", root_dir=root, recursive=True):
		print(root,"\\",name, sep='')
		text = load_text(root / name)
		patcher.add_patch(name, text)
load_patches(data_dir / "patches_jp_switch")
patcher.run()

compile_scripts(dst_script_dir, patch_scs_dir, flag_set)

out_dir.mkdir(parents=True, exist_ok=True)
shutil.copytree(dst_script_dir, out_dir / "script", dirs_exist_ok=True)
