"""Script para compilar o Audiolivro em executável usando PyInstaller."""
import subprocess
import sys
from pathlib import Path


def build(onefile: bool = True):
    mode = "--onefile" if onefile else "--onedir"
    print(f"Compilando Audiolivro (Modo: {mode})...")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        mode,
        "--collect-all",
        "customtkinter",
        "--name",
        "Audiolivro",
        "desktop_app.py",
    ]

    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("✅ Executável gerado com sucesso!")
        print(f"📁 Disponível em: {Path('dist').resolve()}")
        print("=" * 50 + "\n")
    else:
        print("\n❌ Falha na compilação.")
        sys.exit(result.returncode)


if __name__ == "__main__":
    onefile = "--onedir" not in sys.argv
    build(onefile=onefile)
