from pathlib import Path
import shutil
import subprocess

src_dir = Path("out/switch_eng")
dst_dir = Path("C:/Games/Ryujinx/portable/mods/contents/0100957016b90000/coz/romfs/")

subprocess.run([
	"python",
	"build_switch_eng.py",
], check=True)

shutil.copytree(src_dir / "script", dst_dir / "script", dirs_exist_ok=True)
