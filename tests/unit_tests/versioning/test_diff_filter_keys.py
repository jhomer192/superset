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
"""Adhoc filters sharing a column must keep distinct identities in the params diff."""

from __future__ import annotations

from typing import Any

from superset.versioning.diff import ChangeRecord, diff_slice_params


def _f(subject: str, operator: str, comparator: Any) -> dict[str, Any]:
    return {
        "expressionType": "SIMPLE",
        "clause": "WHERE",
        "subject": subject,
        "operator": operator,
        "comparator": comparator,
    }


GT1 = _f("sales", ">", 1)
GT2 = _f("sales", ">", 2)
LT10 = _f("sales", "<", 10)
NE7 = _f("sales", "!=", 7)
REGION = _f("region", "==", "EMEA")


def _diff(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> list[ChangeRecord]:
    return diff_slice_params({"adhoc_filters": before}, {"adhoc_filters": after})


def test_removing_one_of_two_same_column_filters_emits_one_remove() -> None:
    records = _diff([GT1, LT10], [LT10])
    assert [r.operation for r in records] == ["remove"]
    assert records[0].from_value == GT1
    assert records[0].path == ["params", "adhoc_filters", "sales|>"]


def test_editing_one_of_two_same_column_filters_emits_one_edit() -> None:
    records = _diff([GT1, LT10], [GT2, LT10])
    assert [r.operation for r in records] == ["edit"]
    assert (records[0].from_value, records[0].to_value) == (GT1, GT2)


def test_adding_third_same_column_filter_emits_one_add() -> None:
    records = _diff([GT1, LT10], [GT1, LT10, NE7])
    assert [r.operation for r in records] == ["add"]
    assert records[0].to_value == NE7


def test_reordering_emits_nothing() -> None:
    assert _diff([GT1, REGION], [REGION, GT1]) == []
    assert _diff([GT1, LT10], [LT10, GT1]) == []


def test_lone_filter_keeps_subject_as_path() -> None:
    records = _diff([GT1], [GT2])
    assert [r.path for r in records] == [["params", "adhoc_filters", "sales"]]


def test_identical_filters_are_numbered_rather_than_collapsed() -> None:
    records = _diff([GT1, GT1], [GT1])
    assert [r.operation for r in records] == ["remove"]
    assert records[0].path == ["params", "adhoc_filters", "sales|>|1|1"]
