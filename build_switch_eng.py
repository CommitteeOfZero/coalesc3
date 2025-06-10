import glob
import json
import os
import shutil
import sys

from argparse import ArgumentParser
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Union

from lib.config import SWITCH_ENG_RESOURCES_PATH
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
	compile_scripts,
	decompile_scripts,
)

arg_parser = ArgumentParser()
arg_parser.add_argument(
	metavar="GAME",
	dest="game",
	choices=(
		"chaos_head_switch",
		"chaos_child_switch"
	),
	help="Game to build patch for."
)

args = arg_parser.parse_args()

flag_set = args.game

data_dir = Path("data")
build_dir = Path(f"build/{ args.game.removesuffix("_switch") }/switch_eng")
out_dir = Path(f"out/{ args.game.removesuffix("_switch") }/switch_eng")

src_dir = build_dir / "src"
dst_dir = build_dir / "dst"

src_script_dir = SWITCH_ENG_RESOURCES_PATH / "script"
raw_scs_dir = build_dir / "scs"
patch_scs_dir = build_dir / "scs-patched"
dst_script_dir = dst_dir / "script"

def load_custom_cls(name: str, platform: str) -> dict[int, str]:
	return load_cls(data_dir / args.game.removesuffix("_switch") / f"cls_swi_eng/{name}.cls")

constants = load_yaml(data_dir / args.game.removesuffix("_switch") / "consts.yaml") or dict()

for arc_name in ["bg", "bgm", "mask", "movie", "script", "se", "voice"]:
	for index, name in load_custom_cls(arc_name).items():
		constants[name.split(".", 1)[0]] = index

if not raw_scs_dir.exists():
	decompile_scripts(raw_scs_dir, src_script_dir, flag_set)

if (args.game == "chaos_head_switch"):
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
load_patches(data_dir / args.game.removesuffix("_switch") / "patches_common")
load_patches(data_dir / args.game.removesuffix("_switch") / "patches_switch")
txt_dir = data_dir / args.game.removesuffix("_switch") / "txt_eng"
TranslationProcessor(patcher, "10_translation/", txt_dir, False, None, '.sct').run()
patcher.run()

compile_scripts(dst_script_dir, patch_scs_dir, flag_set)

out_dir.mkdir(parents=True, exist_ok=True)
shutil.copytree(dst_script_dir, out_dir / "script", dirs_exist_ok=True)
