# Travel expense receipt automation

## Decision

Use a deterministic Python worker plus a small OpenClaw skill/tool surface. The
worker owns Gmail discovery, nested MIME extraction, bounded ZIP/OFD inspection,
document identity, trip reconciliation, file transactions, audit state and
Nextcloud sync. The skill only explains status and mediates explicit owner choices.
An LLM must not place documents or decide that a journey is complete.

## Data flow and states

Every ten minutes, the collector searches messages since a committed Gmail cursor,
downloads RFC822 content, recursively inventories forwarded messages and records
blobs by SHA-256. Archive readers reject encrypted entries, absolute/parent paths,
symlinks, excessive file counts, expansion size and compression ratio. Documents
move through `observed -> extracted -> classified -> matched -> committed`; an
uncertain item uses `needs_review`, and failures never advance its source cursor.

Trip states are `open`, `return_observed`, `closed`, and `reopened`. A trip begins
with a Wuhan departure. Transport segments form a time-ordered route graph; a
return to Wuhan makes it a closure candidate. The default 72-hour observation
period allows late credentials. Late invoices may reopen the same trip. Hotel
receipts require overlapping stay dates and a city on the trip. Refund fees require
a unique traveler/time/route association and may coexist with an executed rail or
flight segment. Exact invoice/document identities and content hashes prevent
duplicates across forwards and formats.

At 22:10 Asia/Shanghai, reconciliation checks open trips, overdue flight boarding
credentials, pending classifications and sync status. Missing credentials and
ambiguities are sent once per stable problem version to the exact Feishu owner.
Routine successful ingestion stays silent. A sync is also attempted after a
committed batch; a host-wide lock prevents concurrent Nextcloud CLI runs.

## Files

The local Nextcloud root is `/home/Daniel/nextcloud`. Final documents are stored at:

```text
documents/出差报销/YYYY/MM月DD日城市、城市/
  交通/
  住宿/
  退票费/
  登机凭证/
  manifest.json
```

The directory date is the first departure from Wuhan. Destinations are actual
prefecture-level stop cities, not stations, districts or transfer-only cities.
Original PDF/OFD/XML files are retained; ZIP and duplicate representations are
recorded in the manifest. Temporary and unresolved blobs remain outside Nextcloud
in a 0700 application state directory and are covered by the encrypted US1 backup.

## Digest boundary

The collector and mail digest share one deterministic candidate classifier. Travel
transport, accommodation, refund and boarding-credential messages are suppressed
from normal briefings after durable ingestion. Non-travel invoices (for example
association, general insurance or dining without trip evidence) stay in the normal
digest. Unknown invoice-like messages stay in the digest with a concise uncertainty
label and are also queued for review; suppression cannot be based only on a broad
word such as “发票”. Inbox cleanup may trash a travel source only after ingestion is
durable. Archived mail remains untouched under the configured mail policy.

## Safety and secrets

State and audit records contain hashes and minimal provenance, not mail bodies.
Feishu notices redact full invoice/identity numbers. Gmail messages are moved only
to Trash, never permanently deleted. Nextcloud credentials must be loaded from a
0600 environment file; credentials embedded in a sync script are not acceptable.
Synchronization must check the CLI exit status and retain an actionable failure
record. Production enablement requires sanitized fixtures for every observed format,
unit/causal tests, an isolated filesystem integration test, dry-run Gmail discovery,
and one read-back-verified Nextcloud test directory before live scheduling.
On a fresh production ledger, run `openclaw-expense-receipts --initialize-cursor-now`
once before enabling collection so historical mail is not silently imported.
