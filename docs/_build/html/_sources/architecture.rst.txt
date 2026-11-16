Architecture and testing
========================

Responsibilities
----------------

``models`` owns roles, publication data and constraints. ``forms`` allowlists
editable fields and restricts affiliation choices. ``views`` handles browser
requests with authentication, ownership and CSRF boundaries. ``api`` and
``serializers`` provide the token/session API and validate submitted data.
``services`` owns approval and delivery, so HTML and API paths share the same
workflow rather than duplicating side effects.

User role groups are synchronised with application permissions. An inactive
account is never a subscription candidate. Role-inapplicable relationship
properties return None; the underlying many-to-many relations are not nullable.
The Planning directory contains the database and approval sequence diagrams.

Security decisions
------------------

Querysets hide drafts from readers and other journalists, including guessed
URLs. Mutation endpoints enforce permissions independently of visible buttons.
Browser mutations use POST and CSRF checks; deletion requires confirmation.
Publisher membership is checked by both forms and serializers. Newsletter
representations also filter articles that have returned to draft.

The recipient union adds a publisher filter only for a non-NULL publisher.
Otherwise readers with no publisher subscriptions could accidentally match
independent articles. Approval and delivery ledgers are persisted and locked
so ordinary retries retain successful steps. The separate HTTP receiver logs
each approved article once.

Verification
------------

The suite covers roles, ownership, draft privacy, subscriptions, newsletters,
CSRF/XSS, deletion, email/HTTP failures and repeated approvals. Security tests
use an explicitly CSRF-enforcing client and script payloads to explain the
threat rather than merely asserting an HTTP code. A LiveServerTestCase makes
a real requests POST to the application's internal API. Expected simulated
failure warnings are not test failures when the suite finishes with OK.

Build documentation with warnings treated as errors. Documentation imports
use an explicit SQLite setting so reading docstrings requires no live DB;
application validation and release tests still run against MariaDB.
