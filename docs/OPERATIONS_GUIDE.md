# Daily operations in YachtPlus

The dashboard, container views, Tasks, Compose preview, volume backups, update
plans and activity search share the same navigation and feedback patterns.
New schedules are disabled until an administrator explicitly saves an enabled
policy. Existing containers and Compose projects are not automatically changed.

## Dashboard and saved container views

The dashboard publishes a snapshot only after container inventory, overview and
usage requests succeed. A connection failure preserves the last successful
snapshot with an explicit warning and timestamp. Unavailable data is not an
empty installation. Polling pauses in a hidden tab and resumes when it returns.
Problem containers appear first, with a textual reason where Docker supplies it.
The running, stopped and unhealthy counters open the corresponding container
filters. Stopped means exited, stopped or dead; paused and created are separate.

The container list supports status, health, stack and update filters alongside
its existing search and column chooser. Save a named view to keep this selection,
apply or replace it later, or remove it. Preferences are stored per account name
in this browser, with a maximum of 20 views. They contain display preferences,
never container configuration or environment values. Browser storage is optional;
blocked or invalid storage does not prevent using the list. An update that has
not been checked is not presented as a confirmed available update.

Navigation, tables and dialogs support keyboard focus and smaller screens.
Reduced-motion preferences disable decorative animations. Product controls use
English consistently; dates follow the browser locale unless explicitly UTC.

## Tasks

Open **Tasks** for container actions and deployments, image pulls and updates,
stack actions, backups, restores and scheduled updates. Each entry records the
resource, actor, status, actual phase and start/finish times. Progress phases
reflect completed handoffs; a percentage is not invented for Docker operations
that do not report one.

Work continues when a page is closed. The initial HTTP 202 means accepted, not
successful. The client follows the task until it succeeds or fails. If monitoring
loses its connection or times out, open Tasks and verify the result before
submitting the action again. Filters and task details are also available through
`/#/tasks?operation=<task-id>`.

The service accepts at most 32 pending/in-progress tasks per API worker and runs
at most two simultaneously. Requests beyond that limit receive 429. Workers
refresh leases every five seconds; an unfinished task without a fresh lease is
marked interrupted after 30 seconds. Work is not silently replayed after restart.
A YachtPlus self-update requires verification after the handoff to its separate
worker; acceptance alone is not reported as successful replacement.

Users see their own account's tasks; active administrators can inspect all tasks.
A stable account-instance identifier prevents a recreated account from inheriting
history if the database reuses its numeric ID. Password changes preserve history
but queued work still rechecks current credentials and permissions. Deployment
payloads and secret values are not stored in task records. Generic Retry is only
available for allowlisted operations whose inputs can be reconstructed safely;
custom scheduled/backup/deployment runners require their original workflow.

## Preview Compose changes

Open a stack editor, modify the YAML, then choose **Preview changes**. The server
validates bounded YAML without modifying any project file. The preview shows:

- affected services;
- the normalized result, including automatically added restricted defaults;
- a comparison against the saved Compose file;
- a downloadable complete diff when the visible preview is truncated.

Review and acknowledge the current preview before saving. Editing the name or
content invalidates that acknowledgement. If another save changes the source
file, saving an older preview returns 409 and requires a new preview. Writes are
serialized across API processes. Navigating away or closing the browser warns
about unsaved edits; draft YAML remains in memory rather than browser storage.

Preview and raw YAML writes require an active administrator and reject API keys.
The existing write endpoint remains compatible with clients that do not send the
optional preview token. Saving does not itself recreate running services.

## Volume backups and restoration

Open **Backups** and choose an ordinary local Docker volume. The source is mounted
read-only into a restricted helper that is never started. YachtPlus streams
Docker's archive API, validates the archive and saves it atomically with SHA-256
metadata. Helpers have no network, capabilities, host socket or host-path mount.
No archive is extracted into the API container's filesystem.

For a consistent backup, stop application writes using the application's own
procedures. YachtPlus does not stop containers automatically. A volume attached
to a running application requires explicit acknowledgement; that backup is only
crash-consistent and may need application-specific recovery. Database dumps remain
the appropriate method when the database requires them.

Supported archives contain regular files and directories. Symlinks, hard links,
special files, traversing/absolute paths, duplicate entries and oversized metadata
are rejected. Infrastructure volumes and custom volume drivers or driver options
are excluded. The default maximum archive size, including tar overhead, is 1 GiB;
the parser also bounds entry count, metadata and execution time. Temporary staging
uses private backup storage, not the small `/tmp` tmpfs, so allow sufficient disk
space for both the archive and staging. Archive/restore storage failures fail
their tasks. Retention failures preserve the successful backup and are reported
separately on its schedule.

The restore wizard verifies the checksum and contents, requires a **new** volume
name, and asks for confirmation. An existing destination is refused, including
concurrent creation detected through transaction labels. Restored ownership is
normalized to UID/GID `1000:1000`; application permissions must be compatible.
Check the new volume with the application before switching it into production.
The source volume is never replaced. Active restores protect their source archive
from ordinary deletion and retention cleanup.

Daily schedules specify a UTC hour/minute and keep the newest 1–30 completed
archives for that volume, including manually created archives. They run while
YachtPlus is available. Retention runs after a successful scheduled backup. An
administrator credential/permission change invalidates the schedule's approval;
review and save it again. A failed scan, full queue or failed archive is shown
rather than reported as success. Delete an unwanted schedule explicitly.

Archives are unencrypted tar files protected by private filesystem permissions
and remain on this server. Copy the backup storage to independent storage
for disaster recovery; settings export and support bundles do not back up volume
contents. There is no arbitrary archive-upload or in-place restore endpoint.

| Setting | Default | Purpose |
|---|---|---|
| `BACKUP_DIR` | `/config/backups` | Private persistent archive and staging directory; no symlink path components. |
| `BACKUP_HELPER_IMAGE` | auto | Existing local image for never-started archive helpers; defaults to the current YachtPlus image. Images declaring extra volumes are refused; no image is pulled automatically. |
| `BACKUP_MAX_BYTES` | `1073741824` | Maximum archive/staging size including tar overhead; minimum 10 KiB. |

## Project update plans

Open **Settings → Update plans**. Each discovered Compose project can use the
existing global setting or an explicitly saved policy with:

- enabled/disabled state and exclusion from automatic updates;
- starting weekdays and a maintenance window, expressed in UTC;
- the minimum number of days between attempts;
- last attempt/result and the next eligible time.

A window crossing midnight belongs to the weekday on which it begins. Use
00:00–24:00 for an all-day window. Saved plans override the global
`COMPOSE_AUTO_UPDATE` cycle, including disabled plans and exclusions. **Use global
setting** removes that override and warns if doing so re-enables global updates.
Manual updates remain available.

The elected scheduler checks policies every minute. Queued work rechecks the
project, plan revision, approving administrator and window before pulling, and
again immediately before service recreation. A long pull or executor wait does
not authorize a restart outside the window. Task acceptance and policy linkage
are committed together. A changed credential/permission requires renewed approval
by saving the plan. Scheduled tasks cannot bypass these checks through generic
Retry. The last attempt consumes its cadence even if the update fails; inspect
Tasks and retry through the intended manual workflow when appropriate.

## Activity search and CSV export

**Settings → Audit Logs** supports exact user/action filters, a literal resource
substring, and a local-time date range converted to UTC for server queries.
Pagination and counts apply to the same filters; results have stable newest-first
ordering. CSV uses the applied filters and contains at most the newest 5,000
matching entries. Narrow the range for a complete export. Spreadsheet formula
prefixes are neutralized, and CSV responses are not cached. The activity log
remains administrator-only and subject to the configured audit retention.

## Upgrade and verification

Startup runs Alembic before serving requests. Revisions `20261027_0001` through
`20261027_0003` add operations, a stable account-instance ID, backup metadata and
update plans. Existing credential versions are preserved; the migration does not
require a new JWT format. Back up the database, signing key and Fernet salt before
upgrading as usual. New feature policies start inactive.

Release verification includes both complete test suites, publication/security
script tests, fresh and existing SQLite migration checks, a production frontend
build with bundle limits, image content/start/health checks, browser checks and a
real volume archive/restore roundtrip. See the current changelog for exact results
and remaining platform limitations.

Docker builds can optionally mount a trusted CA without baking it into image
layers: `docker build --secret id=proxy_ca,src=/path/to/ca-bundle.pem .`.
The Docker CLI comes from a digest-pinned official CLI stage; the Compose download
retains checksum validation. Both supplied Compose stacks include the internal
`dockerproxy` host in `NO_PROXY`/`no_proxy`, preserving additional configured hosts.
This keeps local Docker API calls on their intended private network when an HTTP
proxy is configured.
