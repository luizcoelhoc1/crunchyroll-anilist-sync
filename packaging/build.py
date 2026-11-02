"""Compila, verifica e só então registra a nova versão do instalador."""
import os
import subprocess
import sys

from build_version import PROJECT, next_version, read_version


def compile_installer(project=PROJECT, requested=""):
    build_dir = project / "build"
    build_dir.mkdir(exist_ok=True)
    lock = build_dir / ".compile.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise RuntimeError(
            "Já existe uma compilação em andamento. Se ela foi interrompida, "
            "remova build/.compile.lock antes de tentar novamente."
        ) from None
    try:
        with handle:
            handle.write(str(os.getpid()))
        version = next_version(read_version(project), requested)
        environment = dict(os.environ, APP_BUILD_VERSION=version)
        print(f"Compilando instalador {version}...", flush=True)
        subprocess.run([sys.executable, str(project / "packaging" / "windows.py"),
                        "--quiet", "bdist_msi"], cwd=project, env=environment, check=True)
        subprocess.run([sys.executable, str(project / "packaging" / "verify.py")],
                       cwd=project, env=environment, check=True)
        version_file = project / "VERSION"
        temporary = version_file.with_suffix(".tmp")
        temporary.write_text(version + "\n", encoding="utf-8")
        temporary.replace(version_file)
        print(f"Versão atualizada para {version} em VERSION.", flush=True)
        return version
    finally:
        lock.unlink()


if __name__ == "__main__":
    try:
        compile_installer(requested=os.environ.get("APP_BUILD_VERSION", ""))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Falha na compilação: {exc}", file=sys.stderr)
        sys.exit(1)
