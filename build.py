import glob, shutil, os

from argparse import ArgumentParser
from pathlib import Path

from lib.config import (
    SWITCH_ENG_RESOURCES_PATH,
	SWITCH_JPN_RESOURCES_PATH,
	WINDOWS_RESOURCES_PATH	
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

	spec: dict = load_yaml(data_dir / "games.yaml")

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
		choices=("switch", "windows"),
		help="Platform to build patch for."
	)

	arg_parser.add_argument(
		metavar="LANG",
		dest="lang",
		choices=("eng", "jpn", "all"),
		help="Language to build patch for."
	)

	args = arg_parser.parse_args()

	if (spec[args.game]["platform"][args.platform].get("multilang", False) and args.lang != "all"):
		print(f"Error: Game '{ args.game }' for platform '{ args.platform }' only supports 'all' language option.")
		return
	if (not spec[args.game]["platform"][args.platform].get("multilang", False) and args.lang == "all"):
		print(f"Error: Game '{ args.game }' for platform '{ args.platform }' doesn't support multilanguage building.")
		return
	if (args.lang not in spec[args.game]["platform"][args.platform].get("langs", [])):
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
		case "windows":
			src_script_dir = src_dir / "script"
		case _:
			raise Exception("Unsupported platform.")

	raw_scs_dir = build_dir / "scs"
	patch_scs_dir = build_dir / "scs-patched"
	dst_script_dir = dst_dir / "script"

	def load_custom_cls(name: str) -> dict[int, str]:
		return load_cls(data_dir / args.game / f"cls_{ args.platform[:3] }{ lang_suffix }/{name}.cls")

	def unpack_archive(dst_dir: Path, arc_name: str) -> None:
		archive_type = spec[args.game]["platform"][args.platform]["archive"]
		archive_path = WINDOWS_RESOURCES_PATH[args.game] / f"{ arc_name }{ archive_type }"
		entries = load_custom_cls(arc_name)
		if os.path.exists(dst_dir) and not args.clean: return
		match archive_type:
			case ".mpk":
				unpack_mpk(dst_dir, archive_path, entries)
			case ".cpk":
				unpack_cpk(dst_dir, archive_path, entries)

	def repack_archive(arc_name: str, src_dir: Path) -> None:
		archive_type = spec[args.game]["platform"][args.platform]["archive"]
		match archive_type:
			case ".mpk":
				run_command("cp", WINDOWS_RESOURCES_PATH[args.game] / "script.mpk", out_dir / "enscript.mpk")
				pack_mpk(out_dir / f"enscript.mpk", src_dir, load_custom_cls(arc_name))
			case ".cpk":
				pack_cpk(out_dir / f"c0{ arc_name }.cpk", src_dir, load_custom_cls(arc_name))

	if args.platform == "windows":
		match spec[args.game]["platform"][args.platform].get("archive", ""):
			case ".cpk":
				unpack_archive(src_script_dir, "script")
				unpack_archive(src_script_dir / "mes00", "mes00")
				unpack_archive(src_script_dir / "mes01", "mes01")
			case ".mpk":
				unpack_archive(src_script_dir, "script")
			case _:
				raise Exception("Missing archive format.")


	constants = load_yaml(data_dir / args.game / "consts.yaml") or dict()

	for arc_name in ["bg", "bgm", "mask", "movie", "script", "se", "voice"]:
		for index, name in load_custom_cls(arc_name).items():
			constants[name.split(".", 1)[0]] = index

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
		spec[args.game]["platform"][args.platform]["in_fmt"],
		spec[args.game]["platform"][args.platform]["out_fmt"],
		spec[args.game]["platform"][args.platform].get("line_inc", 100)
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
			spec[args.game]["versioned"]
		).run()

	patcher.run()

	compile_scripts(dst_script_dir, patch_scs_dir, flag_set, spec[args.game]["platform"][args.platform]["charset"])

	out_dir.mkdir(parents=True, exist_ok=True)

	match args.platform:
		case "switch":
			shutil.copytree(dst_script_dir, out_dir / "script", dirs_exist_ok=True)
		case "windows":
			match spec[args.game]["platform"][args.platform].get("archive", ""):
				case ".cpk":
					repack_archive("script", dst_script_dir)
					repack_archive("mes00", dst_script_dir / "mes00")
					repack_archive("mes01", dst_script_dir / "mes01")
				case ".mpk":
					repack_archive("script", dst_script_dir)
				case _:
					raise Exception("Missing archive format.")

if __name__ == "__main__":
	main()