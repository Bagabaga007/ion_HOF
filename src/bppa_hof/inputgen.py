"""QM 输入文件生成: Gaussian (.gjf) 与 ORCA (.inp)。

对照文档采用的计算水平:
  - 结构优化+频率: RIJCOSX-B3LYP/def2-SVP        (ORCA)
  - 高精度单点:    M06-2X/def2-TZVP (可换 G4/ccCA 等)
  - 组合方法 G4:   Gaussian G4
  - 分子体积:      B3LYP/def2-SVP + Volume (Gaussian, 0.001 e/Bohr^3 等值面)
  - 单原子单点:    与目标同水平, 多重度 C=3/H=2/N=4/O=3/F=2/Li=2

低阶渲染函数 (gaussian_input / orca_input) + 预设配方 (recipes) + 面向离子/单原子
的成套输入生成 (ion_inputs / atom_inputs)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .geometry import Molecule, single_atom


# ---------------------------------------------------------------------------
# 低阶渲染
# ---------------------------------------------------------------------------
def gaussian_input(
    molecule: Molecule,
    route: str,
    *,
    nprocshared: int = 32,
    mem: str = "64GB",
    chk: Optional[str] = None,
    title: Optional[str] = None,
    extra_tail: str = "",
) -> str:
    """渲染 Gaussian .gjf 文本。

    route 例: "#p G4" 或 "#p B3LYP/def2SVP Opt Freq Volume"。
    """
    lines: list[str] = []
    if nprocshared:
        lines.append(f"%nprocshared={nprocshared}")
    if mem:
        lines.append(f"%mem={mem}")
    if chk:
        lines.append(f"%chk={chk}")
    route = route if route.lstrip().startswith("#") else f"#p {route}"
    lines.append(route)
    lines.append("")
    lines.append(title or molecule.name)
    lines.append("")
    lines.append(f"{molecule.charge} {molecule.multiplicity}")
    lines.append(molecule.coordinate_block())
    lines.append("")  # 坐标块后需空行
    text = "\n".join(lines)
    if extra_tail:
        text += "\n" + extra_tail.rstrip("\n") + "\n"
    return text + "\n"


def orca_input(
    molecule: Molecule,
    keywords: str,
    *,
    nprocs: int = 32,
    maxcore_mb: int = 2000,
    blocks: str = "",
) -> str:
    """渲染 ORCA .inp 文本。

    keywords 例: "RIJCOSX B3LYP def2-SVP def2/J Opt Freq" (不含前导 '!')。
    """
    keywords = keywords.lstrip("! ").strip()
    lines: list[str] = [f"! {keywords}"]
    if nprocs and nprocs > 1:
        lines.append(f"%pal nprocs {nprocs} end")
    if maxcore_mb:
        lines.append(f"%maxcore {maxcore_mb}")
    if blocks:
        lines.append(blocks.rstrip("\n"))
    lines.append(f"* xyz {molecule.charge} {molecule.multiplicity}")
    lines.append(molecule.coordinate_block())
    lines.append("*")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 预设配方 (对照文档计算水平)
# ---------------------------------------------------------------------------
@dataclass
class GaussianRecipe:
    route: str
    nprocshared: int = 32
    mem: str = "64GB"
    use_chk: bool = True


@dataclass
class OrcaRecipe:
    keywords: str
    nprocs: int = 32
    maxcore_mb: int = 2000
    blocks: str = ""


# Gaussian 预设
G4 = GaussianRecipe(route="#p G4")


def gaussian_volume_recipe(mc_points: int = 10000) -> GaussianRecipe:
    """B3LYP/def2-SVP 结构优化+频率+分子体积 (0.001 e/Bohr^3)。

    mc_points: 蒙特卡洛体积采样点数 (文档指标2取 10000; 3.2 取 5000)。
    通过 IOp(6/45=N) 设置; 若你的 Gaussian 版本不支持, 请改用 Volume=Tight。
    """
    route = f"#p B3LYP/def2SVP Opt Freq Volume IOp(6/45={mc_points})"
    return GaussianRecipe(route=route)


# ORCA 预设
ORCA_OPT_FREQ = OrcaRecipe(keywords="RIJCOSX B3LYP def2-SVP def2/J Opt Freq")
# ORCA 的 Minnesota functional 关键字不含连字符：M062X（不是 M06-2X）。
ORCA_HIGH_SP = OrcaRecipe(keywords="M062X def2-TZVP def2/J")


def build_gaussian(molecule: Molecule, recipe: GaussianRecipe) -> str:
    chk = f"{molecule.name}.chk" if recipe.use_chk else None
    return gaussian_input(
        molecule,
        recipe.route,
        nprocshared=recipe.nprocshared,
        mem=recipe.mem,
        chk=chk,
    )


def build_orca(molecule: Molecule, recipe: OrcaRecipe) -> str:
    return orca_input(
        molecule,
        recipe.keywords,
        nprocs=recipe.nprocs,
        maxcore_mb=recipe.maxcore_mb,
        blocks=recipe.blocks,
    )


# ---------------------------------------------------------------------------
# 成套输入生成
# ---------------------------------------------------------------------------
def ion_inputs(
    molecule: Molecule,
    *,
    program: str = "orca",
    high_level_sp: bool = True,
    optimized_molecule: Optional[Molecule] = None,
    volume: bool = True,
    mc_points: int = 10000,
) -> dict[str, tuple[str, str]]:
    """为一个离子生成成套输入, 返回 {用途: (文件名, 文本)}。

    program="gaussian": 生成 G4 能量输入 + (可选) 体积输入。
    program="orca":     生成 opt+freq 输入；仅在提供 optimized_molecule 时
                        生成高精度单点输入，避免在未优化结构上误跑 SP；
                        体积计算文档采用 Gaussian, 故 program="orca" 时
                        体积输入仍以 Gaussian 生成。
    """
    program = program.lower()
    out: dict[str, tuple[str, str]] = {}
    name = molecule.name

    if program == "gaussian":
        out["energy"] = (f"{name}.gjf", build_gaussian(molecule, G4))
    elif program == "orca":
        out["opt_freq"] = (f"{name}_optfreq.inp", build_orca(molecule, ORCA_OPT_FREQ))
        if high_level_sp and optimized_molecule is not None:
            if optimized_molecule.composition() != molecule.composition():
                raise ValueError("优化结构与原始结构的元素组成不一致")
            if (
                optimized_molecule.charge != molecule.charge
                or optimized_molecule.multiplicity != molecule.multiplicity
            ):
                raise ValueError("优化结构与原始结构的电荷或多重度不一致")
            sp_mol = Molecule(
                atoms=optimized_molecule.atoms,
                charge=molecule.charge,
                multiplicity=molecule.multiplicity,
                name=f"{name}_sp",
            )
            out["sp"] = (f"{name}_sp.inp", build_orca(sp_mol, ORCA_HIGH_SP))
    else:
        raise ValueError(f"未知 program: {program!r} (可选 gaussian/orca)")

    if volume:
        vol_recipe = gaussian_volume_recipe(mc_points)
        vol_mol = Molecule(
            molecule.atoms, molecule.charge, molecule.multiplicity, f"{name}_vol"
        )
        out["volume"] = (f"{name}_vol.gjf", build_gaussian(vol_mol, vol_recipe))
    return out


def atom_inputs(
    elements: list[str],
    *,
    program: str = "gaussian",
) -> dict[str, tuple[str, str]]:
    """为各元素生成单原子输入 (单点), 返回 {元素: (文件名, 文本)}。

    program="gaussian": G4 单原子。 program="orca": 高精度单点 (M06-2X/def2-TZVP)。
    多重度按文档规定自动设置。
    """
    program = program.lower()
    out: dict[str, tuple[str, str]] = {}
    for el in elements:
        atom = single_atom(el)
        if program == "gaussian":
            out[el] = (f"atom_{el}.gjf", build_gaussian(atom, G4))
        elif program == "orca":
            out[el] = (f"atom_{el}.inp", build_orca(atom, ORCA_HIGH_SP))
        else:
            raise ValueError(f"未知 program: {program!r}")
    return out
