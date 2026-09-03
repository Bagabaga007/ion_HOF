"""bppa_hof: 全氮/富氮离子盐生成焓计算工作流。

固态生成焓 = 气相生成焓 (原子化能法) − 晶格焓 (VBT)。
详见《生成焓相关》方法文档 2.2 节。
"""

from .atom_data import AtomData
from .deviation import DeviationReport, deviation_report
from .gas_phase import gas_phase_hof, single_point_atom_enthalpy_hartree
from .geometry import Molecule, single_atom
from .inputgen import (
    atom_inputs,
    build_gaussian,
    build_orca,
    gaussian_input,
    ion_inputs,
    orca_input,
)
from .lattice import lattice_enthalpy_kcal, lattice_energy_kj, ionic_strength
from .models import Ion, QMResult, combine_single_point_and_thermal, parse_formula
from .salt import HofResult, Salt
from .workflow import OrcaThermochemistryResult, run_orca_thermochemistry

__version__ = "0.1.0"

__all__ = [
    "AtomData",
    "Ion",
    "QMResult",
    "Salt",
    "HofResult",
    "Molecule",
    "DeviationReport",
    "parse_formula",
    "combine_single_point_and_thermal",
    "single_atom",
    "gas_phase_hof",
    "single_point_atom_enthalpy_hartree",
    "lattice_enthalpy_kcal",
    "lattice_energy_kj",
    "ionic_strength",
    "deviation_report",
    "gaussian_input",
    "orca_input",
    "build_gaussian",
    "build_orca",
    "ion_inputs",
    "atom_inputs",
    "OrcaThermochemistryResult",
    "run_orca_thermochemistry",
]
