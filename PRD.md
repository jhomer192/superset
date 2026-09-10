# Superset platform requirements (mock PRD)

Requirements the `superset issue finder and fixer` automation verifies on every merge into
`master`. Each requirement has a stable id; the automation's probe registry maps ids to probes
that run against a booted checkout, and a regression issue names the requirement it violates.
A requirement is either held at HEAD or it is not; there is no partial credit.

## Security

### PRD-SEC-1 Cookie security invariants are enforced at startup

Superset refuses to start when `SESSION_COOKIE_SAMESITE="None"` is configured with
`SESSION_COOKIE_SECURE=False`, and logs a WARNING naming `SESSION_COOKIE_SECURE` when the
preferred URL scheme is https but the session cookie is not marked Secure.

### PRD-SEC-2 Unauthenticated API access is rejected

`GET /api/v1/chart/` without a session or bearer token returns HTTP 401.

### PRD-SEC-3 SVG uploads are sanitised idempotently

`sanitize_svg_content` removes script-bearing content and produces the same output when run
twice; sanitising cannot reassemble a removed tag.

## Authentication

### PRD-AUTH-1 Database login issues a bearer token

`POST /api/v1/security/login` with valid database credentials returns HTTP 200 and an
`access_token`; the token authorises `GET /api/v1/me/`.

## Data and SQL

### PRD-SQL-1 KQL statement splitting preserves text before multiline strings

The KQL splitter keeps every statement intact when a statement contains a triple-backtick
multiline string; no text before the string is dropped or merged into a neighbour.

### PRD-SQL-2 Streaming export chunk size is configured once

Chart data export and SQL Lab export read the streaming chunk size from a single configuration
value; neither endpoint hard-codes its own.

## Charts and dashboards

### PRD-CHART-1 Chart history versioning keeps one record per save

The versioning diff keeps every saved chart version and fabricates none when two saves differ
only in nested fields.

### PRD-CHART-2 Custom-tag filters do not corrupt the rison query

Adding a custom tag to a list filter leaves the other filter clauses in the `q` parameter
unchanged.

## Platform

### PRD-OPS-1 Health endpoint

`GET /health` returns HTTP 200 with body `OK` once the app has booted.
