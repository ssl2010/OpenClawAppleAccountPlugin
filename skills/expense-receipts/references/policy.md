# Resolution policy

## Evidence priority

Prefer signed/structured invoice XML, then boarding credentials or ticket fields,
then stable PDF text, then trusted envelope headers. A sender or filename alone may
identify a candidate but cannot prove journey membership. Calendar events are
corroboration, not authority. A reimbursement invoice is not proof that travel
occurred; refund evidence is not proof that the whole trip was cancelled.

## Ambiguity

Show the owner the item type, date, route/city, amount when available, candidate
trip(s), and the exact reason no unique assignment was possible. Do not expose full
invoice numbers, identity numbers, mail bodies, tokens or local paths in Feishu.
Accept a reply only through the configured owner binding. Preview the proposed
assignment before applying it.

## Trip changes

Late receipts may reopen and update a closed trip without creating a second folder.
Folder renames require an atomic local move, manifest commit and successful sync.
If remote synchronization has an unknown result, retain the local transaction and
report it; never repeat destructive moves blindly.

## Mail lifecycle

Receipt ingestion must commit artifact hashes and provenance before the general
Inbox cleanup may trash the source mail. A testing bundle is trashed only after its
formats are represented by sanitized fixtures and the regression suite passes.
Trash is recoverable; permanent deletion is outside this workflow.
