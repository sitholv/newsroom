# News application plan

Vusi Sithole — VS26060020556

## Users and functional requirements

Readers register, log in, read approved articles and newsletters, and manage
their subscriptions to publishers and journalists. They cannot create or edit
editorial content. Journalists create articles and newsletters and update or
delete only their own work. Editors review drafts, update or delete articles,
approve publication and maintain newsletters. A reader must never obtain an
unapproved article by guessing its URL or using the API.

An article has a title, content, journalist author, creation time and approval
state. A publisher is optional so that a journalist can publish independently.
Publishers have multiple journalist and editor members. Newsletters contain
multiple articles. Subscriptions link readers to journalists or publishers.

The first approval creates a durable delivery record. Its recipients are the
deduplicated union of readers following the journalist and publisher. Email
delivery and the required HTTP POST to the local approved-article endpoint
have separate completion flags so a failed HTTP request need not resend mail.
The receiving endpoint authenticates the internal request and stores a unique
article log. The server chooses the destination; clients cannot supply a URL.

## Database design and normalisation

Use a custom AbstractUser model from the first migration. Store role once on
that model and synchronise its managed role group when it changes. Group
permissions express the role rules, with request-level ownership checks in
addition. Each article and newsletter references its author instead of copying
user data. Junction tables implement publisher membership, subscriptions and
newsletter contents. Each pair is unique through Django's many-to-many schema.
Email addresses are unique, avoiding ambiguous registration and subscriptions.

Reader-only and journalist-only public properties return None for other roles.
SQL many-to-many relations cannot themselves hold NULL. Their underlying
tables remain empty for inapplicable roles instead of inserting sentinel rows.
Forms and API validation restrict role-inappropriate relationships.

Use MariaDB for the assessed migration and integration test. A separate SQLite
test option may speed up unit tests, but does not count as MariaDB evidence.
Database credentials come from environment variables and never enter source
control. Docker must use the isolation arrangement confirmed by the user.

## UI and routes

The home screen lists approved stories, with title, journalist, publisher and
publication state where appropriate. A logged-in editorial workspace lists
drafts and provides labelled create, edit and delete actions. Article detail
shows the content, author and approval controls only for editors. Deletion uses
a confirmation page and POST. A subscriptions screen provides separate
publisher and journalist checkboxes for readers. Newsletters have list, detail
and ownership-checked editing screens. Login, registration and logout provide
clear validation and success messages.

At narrow widths, navigation and form controls wrap without horizontal scroll.
Use semantic headings, visible labels, keyboard focus and accessible errors.
Never use colour alone to distinguish a draft from an approved article.

## API contract

Token authentication protects /api/articles/, /api/articles/subscribed/ and
/api/articles/<id>/. Readers receive approved articles only. Creation is
journalist-only. Journalists update/delete their own articles; editors may
update/delete articles and approve them through a separate action. Approval
is not a writable general serializer field. Serialize users, publishers,
articles and newsletters without passwords or tokens in public responses.

## Security, failures and non-functional requirements

Enforce permissions on the server for HTML and API requests. Use CSRF tokens
for browser mutations, Django password hashing and validation, escaped template
content and constrained form fields. Public signup cannot create an editor;
a trusted administrator assigns that role. Use transactions around approval
and record creation, short network timeouts and explicit delivery failure
messages. A repeated approval must not create duplicate logs or resend an
already recorded successful email. SMTP cannot guarantee exactly-once delivery
after a process crash; document this operational limitation honestly.

Tests cover role denial, draft privacy, ownership, subscriptions, newsletter
validation, approval idempotency and email/HTTP failure recovery. A real local
HTTP test and actual MariaDB migration are separate integration checks.
Maintain function/class/test docstrings, explain security decisions in comments
and visually separate settings blocks. Do not submit credentials, databases,
virtual environments, caches or generated static copies.
