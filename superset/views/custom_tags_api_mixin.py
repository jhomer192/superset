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
"""Mixin for APIs that need custom_tags optimization with frontend compatibility."""

from typing import Any

import prison
from flask import current_app, request, Response
from werkzeug.datastructures import ImmutableMultiDict

PUBLIC_TAGS_RELATION = "tags"
OPTIMIZED_TAGS_RELATION = "custom_tags"
COLUMN_LIST_KEYS = ("columns", "select_columns")


def _rewrite_column(column: Any) -> Any:
    """Map a FAB column reference from the public ``tags`` relationship to
    ``custom_tags``.

    Every ``tags.<attribute>`` reference is rewritten, whatever the attribute:
    the whole relationship is what gets renamed, so ``tags.description`` becomes
    ``custom_tags.description`` and is then validated against ``list_columns``
    by FAB like any other column. The bare ``tags`` column is left alone
    because it is a ``search_columns`` entry whose ``search_filters`` (tag id /
    tag name filters) are registered under that exact name. ``custom_tags.*``
    is already in the target form and ``owner_tags.*``-style relations are
    unrelated, so both are returned unchanged, which makes the rewrite
    idempotent.
    """
    if not isinstance(column, str):
        return column
    prefix = f"{PUBLIC_TAGS_RELATION}."
    if column.startswith(prefix):
        return f"{OPTIMIZED_TAGS_RELATION}.{column[len(prefix) :]}"
    return column


def rewrite_tags_rison_query(query_str: str) -> str:
    """Rewrite the ``tags`` column references inside a FAB rison ``q`` string.

    The rison is parsed, the column names in ``columns``, ``select_columns``,
    ``order_column`` and ``filters[].col`` are rewritten on the parsed
    structure, and the result is re-serialised. Filter *values* are never
    touched. A ``q`` that is not parseable rison is returned unmodified so
    FAB's own ``@rison`` decorator still produces its usual 400.
    """
    try:
        parsed = prison.loads(query_str)
    except prison.decoder.ParserException:
        return query_str
    if not isinstance(parsed, dict):
        return query_str

    for key in COLUMN_LIST_KEYS:
        columns = parsed.get(key)
        if isinstance(columns, list):
            parsed[key] = [_rewrite_column(column) for column in columns]
    if "order_column" in parsed:
        parsed["order_column"] = _rewrite_column(parsed["order_column"])
    filters = parsed.get("filters")
    if isinstance(filters, list):
        for filter_ in filters:
            if isinstance(filter_, dict) and "col" in filter_:
                filter_["col"] = _rewrite_column(filter_["col"])

    return prison.dumps(parsed)


class CustomTagsOptimizationMixin:
    """Reusable mixin for APIs that optimize tag queries via custom_tags relationship.

    When enabled via config, this mixin:
    1. Configures list_columns to use custom_tags (filtered relationship)
    2. Exposes custom_tags as tags in the response schema
    3. Rewrites frontend requests from 'tags.*' to 'custom_tags.*'
    4. Transforms responses to rename 'custom_tags' back to 'tags'

    This provides SQL query optimization (97% reduction) while maintaining
    frontend compatibility.

    Usage:
        class MyRestApi(CustomTagsOptimizationMixin, BaseSupersetModelRestApi):
            def __init__(self):
                self._setup_custom_tags_optimization(
                    config_key="MY_API_CUSTOM_TAGS_ONLY",
                    full_columns=FULL_TAG_COLUMNS,
                    custom_columns=CUSTOM_TAG_COLUMNS,
                )
                super().__init__()
    """

    _custom_tags_only: bool

    def _setup_custom_tags_optimization(
        self,
        config_key: str,
        full_columns: list[str],
        custom_columns: list[str],
    ) -> None:
        """Configure custom tags optimization based on config.

        Args:
            config_key: Config key to check (e.g., "DASHBOARD_LIST_CUSTOM_TAGS_ONLY")
            full_columns: list_columns when optimization disabled (includes all tags)
            custom_columns: list_columns when optimization enabled (only custom_tags)
        """
        self._custom_tags_only = current_app.config.get(config_key, False)
        self.list_columns = custom_columns if self._custom_tags_only else full_columns

    def _init_model_schemas(self) -> None:
        """Keep the optimized relationship's public schema name stable."""
        super()._init_model_schemas()  # type: ignore[misc]

        list_model_schema = getattr(self, "list_model_schema", None)
        if (
            self._custom_tags_only
            and list_model_schema
            and "custom_tags" in list_model_schema.fields
        ):
            list_model_schema.fields["custom_tags"].data_key = "tags"

    def get_list(self, **kwargs: Any) -> Response:
        """Override to rewrite request parameters for custom_tags optimization.

        When config is enabled, rewrites 'tags.*' column references to
        'custom_tags.*' in the rison ``q`` so FAB can find the columns in
        list_columns. See ``rewrite_tags_rison_query``.
        """
        if self._custom_tags_only:
            query_str = request.args.get("q", "")
            modified_query = (
                rewrite_tags_rison_query(query_str) if query_str else query_str
            )
            if modified_query != query_str:
                # Temporarily patch request.args
                modified_args = request.args.copy()
                modified_args["q"] = modified_query
                original_args = request.args
                request.args = ImmutableMultiDict(modified_args)

                try:
                    return super().get_list(**kwargs)  # type: ignore
                finally:
                    # Restore original args
                    request.args = original_args

        return super().get_list(**kwargs)  # type: ignore

    def pre_get_list(self, data: dict[str, Any]) -> None:
        """Rename custom_tags → tags in response for frontend compatibility.

        Called by FAB before sending the list response. This ensures the frontend
        always receives 'tags' regardless of backend optimization config.
        """
        if self._custom_tags_only and "result" in data:
            for item in data["result"]:
                if "custom_tags" in item:
                    item["tags"] = item.pop("custom_tags")

        super().pre_get_list(data)  # type: ignore
