from pathlib import Path
import shutil
import subprocess

src_dir = Path("out/windows")
dst_dir = Path("C:/Games/coz/CHAOS;HEAD NOAH/languagebarrier/")

subprocess.run([
	"python",
	"build_windows.py",
], check=True)

shutil.copyfile(src_dir / "script.cpk", dst_dir / "c0script.cpk")
shutil.copyfile(src_dir / "mes00.cpk", dst_dir / "c0mes00.cpk")
shutil.copyfile(src_dir / "mes01.cpk", dst_dir / "c0mes01.cpk")
