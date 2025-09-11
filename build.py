import glob, shutil, os
import sys

from pathlib import Path

from typing import assert_never

from lib.config import RESOURCES_PATH

from lib.ScriptPatcher import ScriptPatcher
from lib.TranslationProcessor import TranslationProcessor
from lib.utils import (
	run_command,
	load_text,
	load_cls,
	load_yaml,
	pack_cpk,
	pack_mpk,
	unpack_cpk,
	unpack_mpk,
	compile_scripts,
	decompile_scripts,
)

from lib.schema import YAML_SCHEMA
from lib.args import ArgumentParserHandler
from lib.types import BuildInfo, ArchiveFormat, ScriptFormat, Language

def main() -> None:
	data_dir = Path("data")

	_spec = YAML_SCHEMA.validate(load_yaml(data_dir / "games.yaml"))
	_args = ArgumentParserHandler().validate_against_spec(_spec)

	build_info = BuildInfo.from_validated(_spec, _args)

	lang_suffix = "" if build_info.selected == "all" else f"_{ build_info.selected }"

	build_dir = Path(f"build/{ build_info.game }/{ build_info.platform }{ lang_suffix }")
	out_dir = Path(f"out/{ build_info.game }/{ build_info.platform }{ lang_suffix }")

	dst_dir = build_dir / "dst"

	src_script_dir: Path 

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
		print(f"[ERROR]\t { err = }")
		sys.exit(1)

	raw_scs_dir = build_dir / "scs"
	patch_scs_dir = build_dir / "scs-patched"
	dst_script_dir = dst_dir / "script"

	def load_custom_cls(name: str) -> dict[int, str]:
		return load_cls(data_dir / build_info.game / f"cls_{ build_info.platform }{ lang_suffix }" / f"{ name }.cls")

	def unpack_archive(dst_dir: Path, arc_name: str, build_info : BuildInfo) -> None:
		if os.path.exists(dst_dir) and not build_info.clean: return

		archive_path : Path = src_script_dir / f"{ arc_name }{ build_info.archive }"
		entries = load_custom_cls(arc_name)

		match build_info.archive:
			case ArchiveFormat.MPK:
				unpack_mpk(dst_dir, archive_path, entries)
				if build_info.in_fmt != ScriptFormat.MST: return

				for lang in build_info.langs:
					unpack_mpk(dst_dir, src_script_dir / f"mes{ +lang:02 }", load_custom_cls(f"mes{ +lang:02 }"))
			case ArchiveFormat.CPK:
				unpack_cpk(dst_dir, archive_path, entries)
			case None:
				assert False, "Unreachable"
			case _:
				assert_never(build_info.archive)

	def repack_archive(arc_name: str, src_dir: Path, build_info : BuildInfo) -> None:
		match build_info.archive:
			case ArchiveFormat.MPK:
				run_command("cp", src_script_dir / "script.mpk", out_dir / "enscript.mpk")
				pack_mpk(out_dir / f"enscript.mpk", src_dir, load_custom_cls(arc_name))
			case ArchiveFormat.CPK:
				pack_cpk(out_dir / f"c0{ arc_name }.cpk", src_dir, load_custom_cls(arc_name))
			case None:
				assert False, "Unreachable"
			case _:
				assert_never(build_info.archive)


	if build_info.archive: unpack_archive(src_script_dir, "script", build_info)

	constants : dict[str, str] = load_yaml(data_dir / build_info.game / "consts.yaml") or dict()

	for arc_name in ["bg", "bgm", "mask", "movie", "script", "se", "voice"]:
		for index, name in load_custom_cls(arc_name).items():
			constants[name.split(".", 1)[0]] = str(index)

	if not raw_scs_dir.exists() or build_info.clean:
		decompile_scripts(raw_scs_dir, src_script_dir, build_info.flag_set, build_info.charset)

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
		build_info.in_fmt,
		build_info.out_fmt,
		build_info.line_inc,
		build_info.save_method
	)
	
	def load_patches(root: Path) -> None:
		for name in glob.glob("**/*.patch", root_dir=root, recursive=True):
			print(root / name, sep='')
			text = load_text(root / name)
			patcher.add_patch(name, text)

	if build_info.selected != Language.JAPANESE:
		load_patches(data_dir / build_info.game / "patches_common")
	
	load_patches(data_dir / build_info.game / f"patches_{ build_info.platform }{ lang_suffix }")

	if build_info.selected != Language.JAPANESE or build_info.selected == "all":
		txt_dir = data_dir / build_info.game / "txt_eng"
		TranslationProcessor(
			patcher,
			"10_translation/",
			txt_dir,
			build_info.game,
			build_info.platform,
			build_info.versioned,
			build_info.comments
		).run()

	patcher.run()

	compile_scripts(dst_script_dir, patch_scs_dir, build_info.flag_set, build_info.charset)

	out_dir.mkdir(parents=True, exist_ok=True)

	match build_info.archive:
		case ArchiveFormat.CPK:
			repack_archive("script", dst_script_dir, build_info)
			if patcher.in_fmt == ".mst":
				repack_archive("mes00", dst_script_dir / "mes00", build_info)
				repack_archive("mes01", dst_script_dir / "mes01", build_info)
		case ArchiveFormat.MPK:
			repack_archive("script", dst_script_dir, build_info)
		case None:
			shutil.copytree(dst_script_dir, out_dir / "script", dirs_exist_ok=True)
		case _:
			assert_never(build_info.archive)

if __name__ == "__main__":
	main()