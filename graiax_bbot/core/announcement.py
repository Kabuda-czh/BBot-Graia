import contextlib
from pathlib import Path
from loguru import logger
from importlib import metadata

try:
    package = metadata.requires("graiax-bbot")
except Exception:
    package = None


TOML_PATH = Path(__file__).parent.parent.parent.joinpath("pyproject.toml")

RAW_TOML = TOML_PATH.read_text(encoding="utf-8") if TOML_PATH.exists() else ""

PROJECT_VERSION = (
    RAW_TOML.split("version = ")[1].split("\n")[0].strip('"')
    if RAW_TOML
    else metadata.version("graiax-bbot")
)

ARIADNE_VERSION = (
    (RAW_TOML.split("version = ")[2].split(", extras")[0].split("\n")[0].strip('"}{^'))
    if RAW_TOML
    else metadata.version("graia-ariadne")
)

BBOT_ASCII_LOGO = rf"""
                     //
         \\         //
          \\       //
    ##DDDDDDDDDDDDDDDDDDDDDD##
    ## DDDDDDDDDDDDDDDDDDDD ##   ________  ________  ________  _________
    ## hh                hh ##  |\   __  \|\   __  \|\   __  \|\___   ___\
    ## hh    //    \\    hh ##  \ \  \|\ /\ \  \|\ /\ \  \|\  \|___ \  \_|
    ## hh   //      \\   hh ##   \ \   __  \ \   __  \ \  \\\  \   \ \  \
    ## hh                hh ##    \ \  \|\  \ \  \|\  \ \  \\\  \   \ \  \
    ## hh      wwww      hh ##     \ \_______\ \_______\ \_______\   \ \__\
    ## hh                hh ##      \|_______|\|_______|\|_______|    \|__|
    ## MMMMMMMMMMMMMMMMMMMM ##
    ##MMMMMMMMMMMMMMMMMMMMMM##  Release {PROJECT_VERSION}. Powered by graia-ariadne {ARIADNE_VERSION}.
        \/            \/"""


def get_monitored_libs():
    monitored_libs = {}
    libs = list(
        filter(
            None,
            RAW_TOML.split("[tool.poetry.dependencies]")[1]
            .split("[tool.poetry.group.dev.dependencies]")[0]
            .split("\n"),
        )
    )
    for lib in libs:
        lib_name, lib_version = lib.split("=", maxsplit=1)
        monitored_libs[lib_name.strip()] = lib_version.strip()
    return monitored_libs


def get_dist_map() -> dict[str, str]:
    """获取与项目相关的发行字典"""

    dist_map: dict[str, str] = {}
    if package:
        for dist in package:
            dist = dist.split()[0].split(";")[0].split("=")[0].split("<")[0].split("[")[0]

            with contextlib.suppress(Exception):
                dist_map[dist] = metadata.version(dist)
    else:
        monitored_libs = get_monitored_libs()
        for dist in metadata.distributions():
            name: str = dist.metadata["Name"]
            if name.lower() in monitored_libs.keys():
                version: str = dist.version
                dist_map[name] = max(version, dist_map.get(name, ""))

    return dist_map


def base_telemetry() -> None:
    """执行基础遥测检查"""
    output: list[str] = [""]
    dist_map: dict[str, str] = get_dist_map()
    output.extend(
        " ".join(
            [
                f"[magenta]{name}[/]:",
                f"[green]{version}[/]",
            ]
        )
        for name, version in dist_map.items()
    )
    output.sort()
    output.insert(0, f"[cyan]{BBOT_ASCII_LOGO}[/]")
    rich_output = "\n".join(output)
    logger.opt(colors=True).info(
        rich_output.replace("[", "<").replace("]", ">"), alt=rich_output, highlighter=None
    )
