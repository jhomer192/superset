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
"""Tests for both renaming mechanisms in ``CustomTagsOptimizationMixin``.

The schema-level ``data_key`` rename only applies to the API's default list
schema; requests that pass ``select_columns`` make FAB build a fresh schema
on the fly, so for those the ``pre_get_list`` response rewrite is what keeps
the public ``tags`` name. Both paths need coverage.
"""

from typing import Any

import prison
import pytest
from flask import current_app, request
from marshmallow import fields, Schema

from superset.views.custom_tags_api_mixin import CustomTagsOptimizationMixin


class BaseApi:
    """Stub for the FAB ``ModelRestApi`` base. The mixin chains via
    ``super()``, so the stub must define the hooks the mixin overrides."""

    list_model_schema: Schema
    pre_get_list_calls: int = 0
    seen_q: str | None = None

    def _init_model_schemas(self) -> None:
        self.list_model_schema = Schema.from_dict(
            {"custom_tags": fields.List(fields.String())}
        )()

    def pre_get_list(self, _data: dict[str, Any]) -> None:
        self.pre_get_list_calls += 1

    def get_list(self, **_kwargs: Any) -> Any:
        # Mirrors FAB's ``@rison`` decorator, which reads ``q`` off request.args
        self.seen_q = request.args.get("q")
        return self.seen_q


class CustomTagsApi(CustomTagsOptimizationMixin, BaseApi):
    _custom_tags_only = True


# Shape the dashboard list search box sends (FilterOperator.TitleOrSlug)
TITLE_SEARCH_Q = (
    "(filters:!((col:dashboard_title,opr:title_or_slug,value:'tags.name migration')))"
)


class UnoptimizedTagsApi(CustomTagsOptimizationMixin, BaseApi):
    _custom_tags_only = False


def test_custom_tags_schema_uses_public_tags_name() -> None:
    api = CustomTagsApi()

    api._init_model_schemas()

    assert api.list_model_schema.dump({"custom_tags": ["critical"]}) == {
        "tags": ["critical"]
    }


def test_custom_tags_schema_keeps_name_when_optimization_disabled() -> None:
    api = UnoptimizedTagsApi()

    api._init_model_schemas()

    assert api.list_model_schema.dump({"custom_tags": ["critical"]}) == {
        "custom_tags": ["critical"]
    }


def test_pre_get_list_renames_custom_tags_when_enabled() -> None:
    api = CustomTagsApi()
    data: dict[str, Any] = {
        "result": [
            {"id": 1, "custom_tags": [{"name": "critical"}]},
            {"id": 2},
        ]
    }

    api.pre_get_list(data)

    assert data["result"][0] == {"id": 1, "tags": [{"name": "critical"}]}
    assert data["result"][1] == {"id": 2}
    assert api.pre_get_list_calls == 1


def test_pre_get_list_keeps_custom_tags_when_disabled() -> None:
    api = UnoptimizedTagsApi()
    data: dict[str, Any] = {"result": [{"id": 1, "custom_tags": []}]}

    api.pre_get_list(data)

    assert data["result"][0] == {"id": 1, "custom_tags": []}
    assert api.pre_get_list_calls == 1


def test_pre_get_list_tolerates_missing_result_key() -> None:
    api = CustomTagsApi()
    data: dict[str, Any] = {"count": 0}

    api.pre_get_list(data)

    assert data == {"count": 0}
    assert api.pre_get_list_calls == 1


def _get_list_q(api: BaseApi, q: str) -> str | None:
    """Run ``get_list`` under a request carrying ``q`` and return the ``q`` the
    FAB base saw. ``q`` is passed via ``query_string`` so it reaches
    ``request.args`` exactly as sent, without URL-encoding surprises."""
    with current_app.test_request_context("/api/v1/dashboard/", query_string={"q": q}):
        api.get_list()
    return api.seen_q


def test_get_list_leaves_filter_values_alone() -> None:
    seen = _get_list_q(CustomTagsApi(), TITLE_SEARCH_Q)

    assert seen is not None
    assert prison.loads(seen) == {
        "filters": [
            {
                "col": "dashboard_title",
                "opr": "title_or_slug",
                "value": "tags.name migration",
            }
        ]
    }


def test_get_list_rewrites_tags_columns() -> None:
    seen = _get_list_q(CustomTagsApi(), "(columns:!(id,tags.name,tags.id,tags.type))")

    assert seen is not None
    assert prison.loads(seen)["columns"] == [
        "id",
        "custom_tags.name",
        "custom_tags.id",
        "custom_tags.type",
    ]


def test_get_list_does_not_bleed_into_other_relations() -> None:
    seen = _get_list_q(CustomTagsApi(), "(columns:!(owner_tags.id))")

    assert seen is not None
    assert prison.loads(seen)["columns"] == ["owner_tags.id"]


def test_get_list_leaves_already_rewritten_columns_alone() -> None:
    seen = _get_list_q(CustomTagsApi(), "(columns:!(custom_tags.id))")

    assert seen is not None
    assert prison.loads(seen)["columns"] == ["custom_tags.id"]


@pytest.mark.parametrize(
    "q",
    [
        "(columns:!(id,tags.name,tags.id,tags.type))",
        TITLE_SEARCH_Q,
        "(columns:!(owner_tags.id,custom_tags.id),order_column:tags.name,"
        "filters:!((col:tags,opr:dashboard_tags,value:3),(col:tags.name,opr:eq,value:x)))",
    ],
)
def test_get_list_rewrite_is_idempotent(q: str) -> None:
    api = CustomTagsApi()

    once = _get_list_q(api, q)
    assert once is not None
    twice = _get_list_q(api, once)
    assert twice is not None

    assert prison.loads(twice) == prison.loads(once)


def test_get_list_rewrites_any_tags_attribute() -> None:
    # Documented choice: the whole ``tags`` relationship is renamed, so an
    # attribute outside id/name/type is rewritten too and left for FAB to
    # validate against list_columns.
    seen = _get_list_q(CustomTagsApi(), "(columns:!(tags.description))")

    assert seen is not None
    assert prison.loads(seen)["columns"] == ["custom_tags.description"]


def test_get_list_rewrites_select_columns_order_column_and_filter_cols() -> None:
    q = (
        "(select_columns:!(tags.id),order_column:tags.name,order_direction:asc,"
        "filters:!((col:tags.name,opr:eq,value:tags.name),(col:tags,opr:dashboard_tags,value:3)))"
    )

    seen = _get_list_q(CustomTagsApi(), q)

    assert seen is not None
    assert prison.loads(seen) == {
        "select_columns": ["custom_tags.id"],
        "order_column": "custom_tags.name",
        "order_direction": "asc",
        "filters": [
            {"col": "custom_tags.name", "opr": "eq", "value": "tags.name"},
            # bare ``tags`` is a search column with its own filters; keep it
            {"col": "tags", "opr": "dashboard_tags", "value": 3},
        ],
    }


def test_get_list_passes_malformed_q_through_unmodified() -> None:
    malformed = "(columns:!(tags.id"

    seen = _get_list_q(CustomTagsApi(), malformed)

    assert seen == malformed


def test_get_list_passes_non_object_rison_through_unmodified() -> None:
    seen = _get_list_q(CustomTagsApi(), "!(tags.id)")

    assert seen == "!(tags.id)"


def test_get_list_without_q_calls_base_untouched() -> None:
    api = CustomTagsApi()

    with current_app.test_request_context("/api/v1/dashboard/"):
        api.get_list()

    assert api.seen_q is None


def test_get_list_does_not_rewrite_when_optimization_disabled() -> None:
    q = "(columns:!(tags.id))"

    seen = _get_list_q(UnoptimizedTagsApi(), q)

    assert seen == q
