import glob, shutil
import sys

from pathlib import Path
from argparse import Namespace, ArgumentError
from config import RESOURCES_PATH

from lib.ScriptPatcher import ScriptPatcher
from lib.TranslationProcessor import TranslationProcessor
from lib.utils import (
	load_text,
	get_custom_cls_loader,
	load_yaml,
	get_archive_unpacker,
	get_archive_repacker,
	compile_scripts,
	decompile_scripts,
)

from lib.schema import YAML_SCHEMA
from lib.args import ArgumentParserHandler
from lib.types import BuildInfo, Language

def main() -> None:
	data_dir = Path("data")

	_spec = YAML_SCHEMA.validate(load_yaml(data_dir / "games.yaml"))
	_args : Namespace

	try:
		_args = ArgumentParserHandler().validate_against_spec(_spec)
	except ArgumentError as err:
		print(f"[ERROR]\t{ err }")
		sys.exit(1)

	build_info = BuildInfo.from_validated(_spec, _args)

	lang_suffix = "" if build_info.selected == "all" else f"_{ build_info.selected }"

	build_dir = Path(f"build/{ build_info.game }/{ build_info.platform }{ lang_suffix }")
	out_dir = Path(f"out/{ build_info.game }/{ build_info.platform }{ lang_suffix }")

	dst_dir = build_dir / "dst"

	src_script_dir: Path
	src_dir = build_dir / "src"

	try:
		match RESOURCES_PATH[build_info.game][build_info.platform]:
			case Path() as path:
				if build_info.selected != "all":
					raise TypeError(f"Expected 'dict[Language, Path]' for game '{ build_info.game }', platform '{ build_info.platform }', language '{ build_info.selected } config, got 'Path' instead")
				src_script_dir = path
			case dict() as lang_dict:
				if build_info.selected == "all":
					raise TypeError(f"Expected 'Path' for game '{ build_info.game }', platform '{ build_info.platform }', language '{ build_info.selected } config, got 'dict[Language, Path]' instead")
				src_script_dir = lang_dict[build_info.selected]
	except TypeError as err:
		print(f"[ERROR]\t { err }")
		sys.exit(1)

	raw_scs_dir = build_dir / "scs"
	patch_scs_dir = build_dir / "scs-patched"

	load_custom_cls = get_custom_cls_loader(data_dir / build_info.game / f"cls_{ build_info.platform }{ lang_suffix }")
	unpack_archive = get_archive_unpacker(src_script_dir, load_custom_cls, build_info)
	repack_archive = get_archive_repacker(src_script_dir, out_dir, load_custom_cls, build_info)

	if build_info.archive: unpack_archive(src_dir, "script")

	constants : dict[str, str] = load_yaml(data_dir / build_info.game / "consts.yaml") or dict()

	for arc_name in ["bg", "bgm", "mask", "movie", "script", "se", "voice"]:
		for index, name in load_custom_cls(arc_name).items():
			constants[name.split(".", 1)[0]] = str(index)

	if not raw_scs_dir.exists() or build_info.clean:
		decompile_scripts(raw_scs_dir, src_dir if build_info.archive else src_script_dir / "script", build_info.flag_set, build_info.charset)

	if build_info.game == "chaos_head" and build_info.selected != Language.JAPANESE:
		with open(raw_scs_dir / "schzdoz_223.scs", "w", encoding="utf-8") as f:
			f.write("0:\n")
		with open(raw_scs_dir / "schzdoz_223.sct", "w", encoding="utf-8") as f:
			pass
		with open(raw_scs_dir / "mes01" / "schzdoz_223_01.mst", "w", encoding="utf-8") as f:
			f.write("0:\n")

	shutil.copytree(raw_scs_dir, patch_scs_dir, dirs_exist_ok=True)
			
	patcher = ScriptPatcher(
		patch_scs_dir,
		build_dir,
		constants,
		build_info
	)
	
	def load_patches(root: Path) -> None:
		for name in glob.glob("**/*.patch", root_dir=root, recursive=True):
			print(root / name, sep='')
			text = load_text(root / name)
			patcher.add_patch(name, text)

	if build_info.selected != Language.JAPANESE:
		load_patches(data_dir / build_info.game / "patches_common")
	
	load_patches(data_dir / build_info.game / f"patches_{ build_info.platform }{ lang_suffix }")

	txt_dir = txt_dir = data_dir / build_info.game / f"txt_{ build_info.selected if build_info.selected != "all" else "eng" }"
	if build_info.selected != Language.JAPANESE or build_info.selected == "all":
		TranslationProcessor(
			patcher,
			"10_translation/",
			txt_dir
		).run()

	patcher.run()

	for raw in glob.glob("**/*.raw", root_dir=txt_dir, recursive=True):
		dst = raw.removesuffix(".raw")
		if dst not in build_info.raw: continue

		shutil.copyfile(txt_dir / raw,  patch_scs_dir / dst, follow_symlinks=True)

	compile_scripts(dst_dir, patch_scs_dir, build_info.flag_set, build_info.charset)

	out_dir.mkdir(parents=True, exist_ok=True)

	if build_info.archive: repack_archive("script", dst_dir)
	else: shutil.copytree(dst_dir, out_dir, dirs_exist_ok=True)

if __name__ == "__main__":
	main()