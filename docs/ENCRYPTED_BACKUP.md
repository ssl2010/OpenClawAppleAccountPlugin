# US1 encrypted backup

Daily at **03:30 Asia/Shanghai**, a systemd user timer writes age-encrypted bundles
to `~/backups/openclaw` (0700). Archives older than 7×24 hours are removed only
after a new backup succeeds and its persisted ciphertext checksum matches.
`Persistent=true` catches up after downtime. No CN1 backups are configured.

## Contents and consistency

- Native `openclaw backup create --verify`: configuration, secrets, agent/session
  state and workspaces, with OpenClaw's database snapshot handling.
- External Google OAuth/keyring, OpenClaw environment files, Apple authentication
  sessions, rail/mail state, systemd user definitions, and custom plugin source.
- Runtime dependencies such as Node, npm packages and Python venv are rebuilt,
  not copied. System packages, unrelated SSH keys, OS and other projects are out
  of scope. External symlink targets are not traversed; re-audit any new custom
  credential locations when configuration changes.

Worker timers pause while active workers finish. The gateway then pauses briefly
while state is captured; active units are restored even when capture fails.
Previously inactive timers remain inactive. Encryption runs after services return.
Private plaintext staging is removed on normal success/failure. A power loss or
SIGKILL can leave a `.staging-*` directory: inspect and remove only that specific
stale directory after confirming no backup is running. This is not secure erase.

The server has only an age **public recipient** at
`~/.config/openclaw-backup/recipient.txt`. Keep the private identity on another
device, outside Git. Losing that key makes these backups unrecoverable.

## Installation and monitoring

Install `age` through the server package manager. Generate an age identity on a
trusted recovery computer; transfer only `age-keygen -y IDENTITY` to the recipient
file. Install the service/timer from `deploy/` in `~/.config/systemd/user/`.
Adjust the service PATH for the installed Node version and source checkout path.
Enable user lingering so scheduling survives logout, then:

```sh
systemctl --user daemon-reload
systemctl --user start openclaw-encrypted-backup.service
systemctl --user enable --now openclaw-encrypted-backup.timer
systemctl --user list-timers openclaw-encrypted-backup.timer
journalctl --user -u openclaw-encrypted-backup.service -n 30
```

Failures are visible in systemd/journal; no daily Feishu notification is installed.
The server cannot test decryption without the private key. Each run verifies the
native archive, external archive readability, age exit status and ciphertext hash;
periodically perform a full decrypt test on the recovery computer.

## Recovery (offline first)

1. Copy the encrypted archive and `.sha256` file to a trusted computer. Verify
   `shasum -a 256 -c ARCHIVE.tar.age.sha256`.
2. Decrypt with `age -d -i IDENTITY -o bundle.tar ARCHIVE.tar.age` into a private
   directory, then extract the three bundle members. Check both inner SHA-256
   hashes against `manifest.json`.
3. Install the recorded OpenClaw version and run `openclaw backup verify` on
   `openclaw.tar.gz`; follow that version's official restore guidance. Inspect
   `external.tar.gz` before extracting under the destination user's home; adapt
   absolute paths/user ownership and install dependencies from lockfiles.
4. Keep gateway, rail and mail workers **stopped** until credentials, state,
   approval settings and timezone have been checked. Restore processing state
   with the application to avoid replaying mail/calendar side effects. Test
   read-only first; never run a restored clone's workers against production.
5. Remove decrypted recovery files when finished and protect the private key.

Server-only retention protects against accidental application changes, **not
server/disk loss or a compromised account deleting backups**. Offsite copies are
a separate deployment decision. GitHub contains source/templates only, no keys,
production configuration, mail, calendar or encrypted runtime archives.

References: [OpenClaw backup](https://docs.openclaw.ai/cli/backup),
[backup safety](https://docs.openclaw.ai/install/backups),
[age](https://github.com/FiloSottile/age).
