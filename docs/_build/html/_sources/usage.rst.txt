Using the newsroom
==================

Readers, journalists and editors
--------------------------------

Register as a reader to follow publishers and journalists. The reading list,
article pages and newsletters show approved content only. Save subscriptions
from the subscriptions screen; they determine your subscribed API feed and
future approval notifications. The local mail backend prints messages in the
server terminal rather than delivering email to real inboxes.

Register as a journalist to create articles and newsletters. Select only a
publisher you belong to, or leave the publisher blank for independent work.
You can change or delete your own work. Editing an approved article returns
it to draft, so an editor must review it again before readers can see it.

Editors are assigned by a trusted administrator through ``/admin/``. Public
registration cannot grant this role. Editors can review drafts and approve,
update or delete articles. Newsletter forms accept approved articles only.
Making someone a Django superuser does not automatically give them the
application's editor role: set the role explicitly.

Approval and recovery
---------------------

Approval is committed before an actual HTTP POST to the internal receiver.
Subscribers to the journalist and publisher are combined without duplicates.
Addresses are sent as BCC, not exposed to other readers. A persisted ledger
tracks email and HTTP independently. Repeat the editor's approval action to
retry incomplete steps; an already recorded email success is not repeated.

A pending notification does not undo article approval. Check the delivery
flags and error text in the read-only admin records. Verify the internal URL
and matching server secret before retrying an HTTP error. Never paste that
secret into a browser form, public issue, Git commit or API token response.
SMTP cannot guarantee exactly-once delivery if the process crashes between
sending a message and saving its completion flag.

API use
-------

POST a registered username/password to ``/api/token/`` to obtain a token.
Send ``Authorization: Token YOUR_TOKEN`` on API requests. Obtain your own
token at runtime; no shared credentials are bundled with the project.

* ``GET /api/articles/``: approved article list.
* ``GET /api/articles/subscribed/``: reader's followed sources.
* ``GET /api/articles/<id>/``: visible article detail.
* ``POST /api/articles/``: journalist creates an article.
* ``PUT`` / ``DELETE /api/articles/<id>/``: authorised owner or editor.
* ``POST /api/articles/<id>/approve/``: editor-only approval and retry.

Clients cannot choose an author or directly set an approval flag. The
internal ``/api/approved/`` receiver requires the server secret and an
already approved article; it is not a public route for bypassing approval.

Setup
-----

The repository README contains the tested virtual-environment and Docker
commands, environment-variable instructions, database health checks and
troubleshooting. Use a separate local database when running the tests.
