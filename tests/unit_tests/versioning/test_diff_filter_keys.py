# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Identity of adhoc filters in the chart-params diff.

Filters are matched across a save by natural key (the ``subject`` column) so
that reordering emits nothing. Two filters on one column — the everyday
``x >= a`` plus ``x <= b`` range — must not collapse into one key, or the
audit log drops the real edit and can report an edit that never happened.
"""

from __future__ import annotations

from typing import Any

from superset.versioning.diff import diff_slice_params


def _f(subject: str, operator: str, comparator: Any) -> dict[str, Any]:
    return {
        "clause": "WHERE",
        "expressionType": "SIMPLE",
        "subject": subject,
        "operator": operator,
        "comparator": comparator,
    }


GT1 = _f("sales", ">", 1)
LT10 = _f("sales", "<", 10)
GT5 = _f("sales", ">", 5)
NE7 = _f("sales", "!=", 7)
REGION = _f("region", "==", "EU")


def _diff(pre: list[dict[str, Any]], post: list[dict[str, Any]]) -> list[Any]:
    return diff_slice_params({"adhoc_filters": pre}, {"adhoc_filters": post})


def test_delete_one_of_two_same_column_filters_emits_remove() -> None:
    records = _diff([GT1, LT10], [LT10])
    assert len(records) == 1
    (rec,) = records
    assert rec.operation == "remove"
    assert rec.from_value == GT1
    assert rec.to_value is None


def test_edit_one_of_two_same_column_filters_emits_edit() -> None:
    records = _diff([GT1, LT10], [GT5, LT10])
    assert len(records) == 1
    (rec,) = records
    assert rec.operation == "edit"
    assert rec.from_value == GT1
    assert rec.to_value == GT5


def test_add_third_same_column_filter_emits_add_only() -> None:
    records = _diff([GT1, LT10], [GT1, LT10, NE7])
    assert [r.operation for r in records] == ["add"]
    assert records[0].from_value is None
    assert records[0].to_value == NE7


def test_reordering_filters_on_different_columns_emits_nothing() -> None:
    assert _diff([GT1, REGION], [REGION, GT1]) == []


def test_reordering_filters_on_same_column_emits_nothing() -> None:
    assert _diff([GT1, LT10], [LT10, GT1]) == []


def test_single_filter_edit_keeps_subject_path() -> None:
    records = _diff([GT1], [GT5])
    assert len(records) == 1
    assert records[0].operation == "edit"
    assert records[0].path == ["params", "adhoc_filters", "sales"]


def test_delete_one_of_two_different_column_filters_emits_remove() -> None:
    records = _diff([GT1, REGION], [REGION])
    assert len(records) == 1
    assert records[0].operation == "remove"
    assert records[0].from_value == GT1


def test_same_column_same_operator_filters_are_distinct() -> None:
    ne1 = _f("sales", "!=", 1)
    ne2 = _f("sales", "!=", 2)
    records = _diff([ne1, ne2], [ne2])
    assert len(records) == 1
    assert records[0].operation == "remove"
    assert records[0].from_value == ne1


def test_identical_duplicate_filters_are_both_kept() -> None:
    records = _diff([GT1, GT1], [GT1])
    assert len(records) == 1
    assert records[0].operation == "remove"
    assert records[0].from_value == GT1


def test_path_elements_are_strings() -> None:
    for records in (_diff([GT1, LT10], [LT10]), _diff([GT1, LT10], [GT1, LT10, NE7])):
        for rec in records:
            assert all(isinstance(p, str) for p in rec.path)
