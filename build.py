import glob, shutil, os

from argparse import ArgumentParser
from pathlib import Path

from typing import Literal, assert_never

from lib.config import (
    SWITCH_ENG_RESOURCES_PATH,
	SWITCH_JPN_RESOURCES_PATH,
	WINDOWS_RESOURCES_PATH,
	PS3_RESOURCES_PATH
)

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

def main() -> None:
	data_dir = Path("data")

	spec = load_yaml(data_dir / "games.yaml")

	arg_parser = ArgumentParser()

	arg_parser.add_argument(
		"--clean",
		action="store_const",
		const=True,
		dest="clean",
		default=False,
		help="Clear cache and build from scratch."
	)

	arg_parser.add_argument(
		metavar="GAME",
		dest="game",
		choices=spec.keys(),
		help="Game to build patch for."
	)

	arg_parser.add_argument(
		metavar="PLATFORM",
		dest="platform",
		choices=("switch", "windows", "ps3"),
		help="Platform to build patch for."
	)

	arg_parser.add_argument(
		metavar="LANG",
		dest="lang",
		choices=("eng", "jpn", "all"),
		help="Language to build patch for."
	)

	args = arg_parser.parse_args()

	if spec[args.game]["platform"][args.platform].get("multilang", False) and args.lang != "all":
		print(f"Error: Game '{ args.game }' for platform '{ args.platform }' only supports 'all' language option.")
		return
	if not spec[args.game]["platform"][args.platform].get("multilang", False) and args.lang == "all":
		print(f"Error: Game '{ args.game }' for platform '{ args.platform }' doesn't support multilanguage building.")
		return
	if args.lang not in spec[args.game]["platform"][args.platform].get("langs", []):
		print(f"Error: Game '{ args.game }' for platform '{ args.platform }' doesn't support language '{ args.lang }'.")
		return

	flag_set = spec[args.game]["platform"][args.platform]["flag_set"]

	lang_suffix = "" if spec[args.game]["platform"][args.platform].get("multilang", False) else f"_{ args.lang }"

	build_dir = Path(f"build/{ args.game }/{ args.platform }{ lang_suffix }")
	out_dir = Path(f"out/{ args.game }/{ args.platform }{ lang_suffix }")

	src_dir = build_dir / "src"
	dst_dir = build_dir / "dst"

	src_script_dir: Path 

	match args.platform:
		case "switch":
			match args.lang:
				case "eng":
					src_script_dir = SWITCH_ENG_RESOURCES_PATH[args.game] / "script"
				case "jpn":
					src_script_dir = SWITCH_JPN_RESOURCES_PATH[args.game] / "script"
				case _:
					raise Exception("Unsupported language.")
		case "windows" | "ps3":
			src_script_dir = src_dir / "script"
		case _:
			raise Exception("Unsupported platform.")

	raw_scs_dir = build_dir / "scs"
	patch_scs_dir = build_dir / "scs-patched"
	dst_script_dir = dst_dir / "script"

	def load_custom_cls(name: str) -> dict[int, str]:
		return load_cls(data_dir / args.game / f"cls_{ args.platform[:3] }{ lang_suffix }/{name}.cls")

	def unpack_archive(dst_dir: Path, arc_name: str) -> None:
		archive_type : Literal[".mpk", ".cpk"] = spec[args.game]["platform"][args.platform]["archive"]
		archive_path : Path

		match args.platform:
			case "windows":
				archive_path = WINDOWS_RESOURCES_PATH[args.game] / f"{ arc_name }{ archive_type }"
			case "ps3":
				archive_path = PS3_RESOURCES_PATH[args.game] / f"{ arc_name }{ archive_type }"
			case _:
				assert(False and "Unreachable")

		entries = load_custom_cls(arc_name)
		if os.path.exists(dst_dir) and not args.clean: return
		match archive_type:
			case ".mpk":
				unpack_mpk(dst_dir, str(archive_path), entries)
			case ".cpk":
				unpack_cpk(dst_dir, str(archive_path), entries)
			case _:
				assert_never(archive_type)

	def repack_archive(arc_name: str, src_dir: Path) -> None:
		archive_type : Literal[".mpk", ".cpk"] = spec[args.game]["platform"][args.platform]["archive"]
		match archive_type:
			case ".mpk":
				run_command("cp", WINDOWS_RESOURCES_PATH[args.game] / "script.mpk", out_dir / "enscript.mpk")
				pack_mpk(out_dir / f"enscript.mpk", src_dir, load_custom_cls(arc_name))
			case ".cpk":
				pack_cpk(out_dir / f"c0{ arc_name }.cpk", src_dir, load_custom_cls(arc_name))
			case _:
				assert_never(archive_type)

	if not spec[args.game]["platform"][args.platform].get("in_fmt", None):
		raise Exception("Missing script format.")
	if spec[args.game]["platform"][args.platform]["in_fmt"] not in [".mst", ".sct"]:
		raise Exception("Unsupported script format.")
	
	in_fmt : Literal[".mst", ".sct"] = spec[args.game]["platform"][args.platform]["in_fmt"]

	if not spec[args.game]["platform"][args.platform].get("out_fmt", None):
		raise Exception("Missing script format.")
	if spec[args.game]["platform"][args.platform]["out_fmt"] not in [".mst", ".sct"]:
		raise Exception("Unsupported script format.")

	out_fmt : Literal[".mst", ".sct"] = spec[args.game]["platform"][args.platform]["out_fmt"]

	if spec[args.game]["platform"][args.platform].get("line_inc", 100) not in [1, 100]:
		raise Exception(f"\"line_inc\" must be one of: [1, 100]")
	
	line_inc : Literal[1, 100] = spec[args.game]["platform"][args.platform].get("line_inc", 100)

	if spec[args.game]["platform"][args.platform].get("archive", None) not in [".cpk", ".mpk"]:
		raise Exception("Unsupported archive format.")

	archive : Literal[".cpk", ".mpk"] | None = spec[args.game]["platform"][args.platform].get("archive", None)

	if args.platform in ["windows", "ps3"]:
		match archive:
			case ".cpk":
				unpack_archive(src_script_dir, "script")
				if in_fmt == ".mst":
					unpack_archive(src_script_dir / "mes00", "mes00")
					unpack_archive(src_script_dir / "mes01", "mes01")
			case ".mpk":
				unpack_archive(src_script_dir, "script")
			case None:
				raise Exception("Missing archive format.")

	constants : dict[str, str] = load_yaml(data_dir / args.game / "consts.yaml") or dict()

	for arc_name in ["bg", "bgm", "mask", "movie", "script", "se", "voice"]:
		for index, name in load_custom_cls(arc_name).items():
			constants[name.split(".", 1)[0]] = str(index)

	if not raw_scs_dir.exists() or args.clean:
		decompile_scripts(raw_scs_dir, src_script_dir, flag_set, spec[args.game]["platform"][args.platform]["charset"])

	if (args.game == "chaos_head" and args.lang != "jpn"):
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
		in_fmt,
		out_fmt,
		line_inc
	)
	
	def load_patches(root: Path) -> None:
		for name in glob.glob("**/*.patch", root_dir=root, recursive=True):
			print(root / name, sep='')
			text = load_text(root / name)
			patcher.add_patch(name, text)

	if args.lang != "jpn":
		load_patches(data_dir / args.game / "patches_common")
	
	load_patches(data_dir / args.game / f"patches_{ args.platform[:3] }{ lang_suffix }")

	if args.lang == "eng" or spec[args.game]["platform"][args.platform].get("multilang", False):
		txt_dir = data_dir / args.game / "txt_eng"
		TranslationProcessor(
			patcher,
			"10_translation/",
			txt_dir,
			args.game,
			args.platform,
			spec[args.game].get("versioned", []),
			spec[args.game].get("comments", [])
		).run()

	patcher.run()

	compile_scripts(dst_script_dir, patch_scs_dir, flag_set, spec[args.game]["platform"][args.platform]["charset"])

	out_dir.mkdir(parents=True, exist_ok=True)

	match args.platform:
		case "switch":
			shutil.copytree(dst_script_dir, out_dir / "script", dirs_exist_ok=True)
		case "windows" | "ps3":
			assert(archive)
			match archive:
				case ".cpk":
					repack_archive("script", dst_script_dir)
					if patcher.in_fmt == ".mst":
						repack_archive("mes00", dst_script_dir / "mes00")
						repack_archive("mes01", dst_script_dir / "mes01")
				case ".mpk":
					repack_archive("script", dst_script_dir)


if __name__ == "__main__":
	main()