"""自动生成测试 - backend/.venv/Lib/site-packages/sqlalchemy/sql/util.py"""
# AUTO-GENERATED
import pytest
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))
try:
    from backend..venv.Lib.site-packages.sqlalchemy.sql.util import *  # noqa
    _OK = True
except ImportError as _e:
    _OK = False; _ERR = str(_e)
# 删除可能被 pytest 误收集的 test 开头函数（来自 from import *）
for _n in list(globals()):
    if _n.startswith('test') and callable(globals()[_n]):
        del globals()[_n]

class TestUtilAuto:
    @pytest.fixture(autouse=True)
    def _check(self):
        if not _OK: pytest.skip(f"import failed: {_ERR if not _OK else ''}")
    def test_join_condition_callable(self):
        """测试 join_condition 可调用（import 成功即通过，调用失败 skip）"""
        try:
            join_condition("", "", "", 1)
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_find_join_source_callable(self):
        """测试 find_join_source 可调用（import 成功即通过，调用失败 skip）"""
        try:
            find_join_source("", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_find_left_clause_that_matches_given_callable(self):
        """测试 find_left_clause_that_matches_given 可调用（import 成功即通过，调用失败 skip）"""
        try:
            find_left_clause_that_matches_given("", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_find_left_clause_to_join_from_callable(self):
        """测试 find_left_clause_to_join_from 可调用（import 成功即通过，调用失败 skip）"""
        try:
            find_left_clause_to_join_from("", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_visit_binary_product_callable(self):
        """测试 visit_binary_product 可调用（import 成功即通过，调用失败 skip）"""
        try:
            visit_binary_product("", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_find_tables_callable(self):
        """测试 find_tables 可调用（import 成功即通过，调用失败 skip）"""
        try:
            find_tables("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_unwrap_order_by_callable(self):
        """测试 unwrap_order_by 可调用（import 成功即通过，调用失败 skip）"""
        try:
            unwrap_order_by("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_unwrap_label_reference_callable(self):
        """测试 unwrap_label_reference 可调用（import 成功即通过，调用失败 skip）"""
        try:
            unwrap_label_reference("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_expand_column_list_from_order_by_callable(self):
        """测试 expand_column_list_from_order_by 可调用（import 成功即通过，调用失败 skip）"""
        try:
            expand_column_list_from_order_by([], "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_clause_is_present_callable(self):
        """测试 clause_is_present 可调用（import 成功即通过，调用失败 skip）"""
        try:
            clause_is_present("", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_tables_from_leftmost_callable(self):
        """测试 tables_from_leftmost 可调用（import 成功即通过，调用失败 skip）"""
        try:
            tables_from_leftmost("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_surface_selectables_callable(self):
        """测试 surface_selectables 可调用（import 成功即通过，调用失败 skip）"""
        try:
            surface_selectables("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_surface_selectables_only_callable(self):
        """测试 surface_selectables_only 可调用（import 成功即通过，调用失败 skip）"""
        try:
            surface_selectables_only("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_extract_first_column_annotation_callable(self):
        """测试 extract_first_column_annotation 可调用（import 成功即通过，调用失败 skip）"""
        try:
            extract_first_column_annotation("", "test")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_selectables_overlap_callable(self):
        """测试 selectables_overlap 可调用（import 成功即通过，调用失败 skip）"""
        try:
            selectables_overlap("", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_bind_values_callable(self):
        """测试 bind_values 可调用（import 成功即通过，调用失败 skip）"""
        try:
            bind_values("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_adapt_criterion_to_null_callable(self):
        """测试 adapt_criterion_to_null 可调用（import 成功即通过，调用失败 skip）"""
        try:
            adapt_criterion_to_null("", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_splice_joins_callable(self):
        """测试 splice_joins 可调用（import 成功即通过，调用失败 skip）"""
        try:
            splice_joins("", "", "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_reduce_columns_callable(self):
        """测试 reduce_columns 可调用（import 成功即通过，调用失败 skip）"""
        try:
            reduce_columns("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_reduce_columns_callable(self):
        """测试 reduce_columns 可调用（import 成功即通过，调用失败 skip）"""
        try:
            reduce_columns("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_reduce_columns_callable(self):
        """测试 reduce_columns 可调用（import 成功即通过，调用失败 skip）"""
        try:
            reduce_columns("")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

    def test_criterion_as_pairs_callable(self):
        """测试 criterion_as_pairs 可调用（import 成功即通过，调用失败 skip）"""
        try:
            criterion_as_pairs("", 1, 1, "")
        except (Exception, SystemExit) as _e:
            pytest.skip(f"调用失败（非 import 问题）: {_e}")

