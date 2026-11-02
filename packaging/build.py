"""Compila, verifica, versiona e publica o instalador no GitHub."""
import hashlib
import json
import os
import subprocess
import sys

from build_version import PROJECT, next_version, read_version
import github_release


def write_version(project, version):
    version_file = project / "VERSION"
    temporary = version_file.with_suffix(".tmp")
    temporary.write_text(version + "\n", encoding="utf-8")
    temporary.replace(version_file)


def build_and_verify(project, environment):
    subprocess.run([sys.executable, str(project / "packaging" / "windows.py"),
                    "--quiet", "bdist_msi"], cwd=project, env=environment, check=True)
    subprocess.run([sys.executable, str(project / "packaging" / "verify.py")],
                   cwd=project, env=environment, check=True)


def compile_installer(project=PROJECT, requested="", publish=False):
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
        pending = build_dir / "pending-release.json"
        if pending.exists():
            if not publish:
                raise RuntimeError("Existe uma publicação pendente. Execute task compile para retomá-la.")
            state = json.loads(pending.read_text(encoding="utf-8"))
            if requested and requested != state["version"]:
                raise RuntimeError("Retome a publicação pendente sem informar outra VERSION.")
            github = github_release.GitHub(project)
            github.prepare(project, state["version"], resume=True)
            if read_version(project) not in (state["previous_version"], state["version"]):
                raise RuntimeError("VERSION mudou desde a compilação pendente.")
            write_version(project, state["version"])
            print("Retomando publicação de v" + state["version"] + "...", flush=True)
            github_release.publish(project, state, pending, github)
            return state["version"]
        current = read_version(project)
        version = next_version(current, requested)
        if publish:
            github = github_release.GitHub(project)
            github.prepare(project, version)
            source = github_release.source_digest(project)
        environment = dict(os.environ, APP_BUILD_VERSION=version)
        print(f"Compilando instalador {version}...", flush=True)
        build_and_verify(project, environment)
        if publish:
            if github_release.source_digest(project) != source:
                raise RuntimeError("O código mudou durante a compilação. Execute task compile novamente.")
            installer = project / "dist" / f"CrunchyrollAniListSync-{version}-x64.msi"
            state = {"version": version, "previous_version": current, "source_digest": source,
                     "repository": github.repository, "branch": github.branch,
                     "sha256": hashlib.sha256(installer.read_bytes()).hexdigest()}
            github_release.save_pending(pending, state)
        write_version(project, version)
        print(f"Versão atualizada para {version} em VERSION.", flush=True)
        if publish:
            github_release.publish(project, state, pending, github)
        return version
    finally:
        lock.unlink()


if __name__ == "__main__":
    try:
        setting = os.environ.get("APP_PUBLISH", "true").lower()
        if setting not in ("true", "false"):
            raise ValueError("PUBLISH deve ser true ou false.")
        compile_installer(requested=os.environ.get("APP_BUILD_VERSION", ""), publish=setting == "true")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Falha na compilação: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr, file=sys.stderr)
        if (PROJECT / "build" / "pending-release.json").exists():
            print("Execute task compile novamente para retomar a mesma publicação.", file=sys.stderr)
        sys.exit(1)
