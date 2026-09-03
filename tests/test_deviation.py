"""偏差分析测试, 锚定文档表15: 三盐 MAE = 1.30 kcal/mol。"""

import pytest

from bppa_hof import deviation_report
from bppa_hof.models import parse_formula

pytestmark = pytest.mark.unit


def test_table15_mae():
    predictions = {"1a+1c": 102.58, "1a+2c": 78.39, "1a+3c": 63.68}
    references = {"1a+1c": 103.70, "1a+2c": 76.49, "1a+3c": 62.80}
    report = deviation_report(predictions, references)
    # 文档: 平均绝对偏差为 1.30 kcal/mol
    assert report.mae == pytest.approx(1.30, abs=0.01)
    assert report.n == 3


def test_per_entry_abs_error():
    report = deviation_report({"a": 102.58}, {"a": 103.70})
    assert report.entries[0].abs_error == pytest.approx(1.12, abs=0.01)


def test_no_common_labels_raises():
    with pytest.raises(ValueError):
        deviation_report({"a": 1.0}, {"b": 2.0})


def test_parse_formula():
    assert parse_formula("N2H5") == {"N": 2, "H": 5}
    assert parse_formula("N5") == {"N": 5}
    assert parse_formula("C2H5N4O2Li") == {"C": 2, "H": 5, "N": 4, "O": 2, "Li": 1}


def test_parse_formula_invalid():
    with pytest.raises(ValueError):
        parse_formula("2N")
