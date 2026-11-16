# Bay Newsroom

Vusi Sithole · VS26060020556

A Django news application with readers, journalists, editors, publisher
memberships, subscriptions, newsletters and an authenticated REST API.

## Setup with MariaDB

Use Python 3.12+, Docker Engine and Docker Compose. On Ubuntu/WSL, mysqlclient
also needs the native build dependencies `python3-dev`, `build-essential`,
`pkg-config` and `default-libmysqlclient-dev`. Install these through your system
package manager before installing Python dependencies.

From this directory, choose local-only passwords and keep them out of Git:

```bash
export DB_PASSWORD='choose-a-local-database-password'
export DB_ROOT_PASSWORD='choose-a-different-local-root-password'
export INTERNAL_APPROVAL_SECRET='choose-a-long-random-local-secret'
docker compose up -d --wait database
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8008
```

Open http://127.0.0.1:8008/. MariaDB is bound only to 127.0.0.1:33316 and uses
the dedicated vs26060020556-newsroom Compose project and its own named volume.
The initialisation SQL grants the application user access to test_newsroom
so Django can create and remove its separate test database. These settings are
for local development, not shared production infrastructure.

The application defaults to MariaDB. Optional environment variables are DB_NAME,
DB_USER, DB_HOST and DB_PORT. NEWSROOM_SQLITE=1 explicitly selects SQLite for
quick isolated checks; it is not the assessed MariaDB configuration. Database
migrations and the test suite were also run against MariaDB successfully.

Stop only this project's containers with `docker compose stop`. Do not use
`down -v` unless you intend to permanently remove this project's saved data.
Changing the password environment variables after initialisation does not change
the credentials stored in an existing database volume.

## Roles and browser workflow

Public signup creates reader or journalist accounts. A trusted superuser uses
/admin/ to assign an editor role and create publishers with editor/journalist
memberships. Role groups and model permissions are synchronised automatically.
An administrator account is not automatically an editor in the application;
assign that role explicitly when testing editorial approval.

Readers can read approved articles and newsletters and manage subscriptions.
Journalists can create and manage their own articles/newsletters, independently
or under a publisher they belong to. Editors review, edit, delete and approve
articles. Editors can create/edit newsletters as allowed by the newsletter
model instructions on page 4 of the brief. Article creation remains
journalist-only. A journalist cannot edit another journalist's content.

Editing an approved article returns it to draft. Drafts are hidden from readers
and from other journalists, including through guessed detail URLs. Publisher
membership is checked when assigning content. Newsletter selections and public
newsletter displays exclude drafts.

## Approval notifications

Approval uses the view/service approach, not an approval signal. After approval
is committed, subscriber addresses from the journalist and publisher are merged
and deduplicated. BCC protects subscriber addresses. Separate persisted flags
track email and the real requests POST to /api/approved/. Repeating approval
retries incomplete steps without resending an email already recorded as sent.

The local mail backend prints to the server terminal. It does not deliver real
email. INTERNAL_APPROVAL_URL defaults to
http://127.0.0.1:8008/api/approved/; change it when using another port. The receiver
requires INTERNAL_APPROVAL_SECRET in its internal header and logs each article
once. Requests have finite connection/read timeouts. A missing secret or service
failure leaves an accurate pending status rather than pretending delivery worked.

SMTP cannot guarantee exactly-once delivery if the process crashes after the
backend accepts a message but before the success flag is saved. The delivery
ledger reduces ordinary retry duplication; it does not hide this limitation.

## REST API

POST /api/token/ with a registered username/password to obtain a token. Supply
Authorization: Token followed by the token value on authenticated requests.
Browser sessions also work with normal CSRF protection. Never commit tokens.

GET /api/articles/ lists approved articles. GET /api/articles/subscribed/
returns the reader's subscribed approved articles. GET /api/articles/<id>/
returns visible details. Journalists can POST /api/articles/ and update/delete
their own details. Editors can update/delete and POST
/api/articles/<id>/approve/. Clients cannot assign an author or directly write
the approval flag. Newsletters have list/create and detail/update/delete routes;
publisher and journalist list endpoints support source discovery.

Serializers for User, Article, Newsletter and Publisher are in
publishing/serializers.py. User responses exclude passwords, tokens and email.
The separate internal receiver is not a public approval shortcut: it accepts
only a configured matching server secret and an already-approved article.

## Automated verification

The code is split by responsibility. publishing/models.py documents fields,
relationships and constraints. publishing/forms.py explains the field
allowlists, filtered publisher choices and newsletter/subscription widgets.
publishing/views.py gives the HTTP methods, context, redirects and access
rules for each screen. API routes and serializers are kept in separate modules.

publishing/services.py explains approval, commit timing, delivery flags and
retry limits. Model clean() is not called automatically by a raw ORM save().
Browser forms run model validation and API serializers perform their own
checks; a new write path must preserve validation and ownership checks.

Security tests explain why CSRF checks are explicitly enabled and why stored
script payloads must be escaped. Notification tests deliberately simulate mail
and HTTP failures, so their warning messages are expected when the suite ends
with OK. The live HTTP test is separate from tests using mocked requests.

With MariaDB running and the same database environment variables exported:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test publishing
```

The suite has 23 tests covering roles, ownership, draft privacy, subscription
filtering, newsletter validation, CSRF/XSS, deletion, mail failure, HTTP failure,
idempotent logging and a real local HTTP publication round trip. The live HTTP
test runs its own temporary server and uses the separate test database; it does
not contact a public service or send real email.

Planning/ contains functional/non-functional requirements, UI plans, database
normalisation and approval-flow diagrams. Each important class, view, service
and test has a docstring; targeted comments explain security and retry choices.

## Before public deployment

Set a private DJANGO_SECRET_KEY, disable DEBUG, configure trusted hosts, HTTPS,
a production server, a real mail backend and secure internal transport. Configure
backups, monitoring and authentication rate limits. No credentials, database
files, virtual environment, caches or collected static copies belong in Git.
