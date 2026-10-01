# CourtLOG Hosting Options — Comparison and Recommendation

**Research date:** 1 October 2026  
**Purpose:** Select a practical hosted staging/showcase environment for the current competition-team prototype. This is an architecture and budget comparison, not a cloud deployment or institutional approval. Prices are USD, before tax, exchange-rate effects, domain costs, and WhatsApp charges; provider prices and availability can change.

## Executive recommendation

For the **21 October 2026 pilot target** and **5 November 2026 competition showcase**, the lowest-change path is a **paid Render web service with a small persistent disk**, running a fresh SQLite database and JWT key pair on that disk. A 512 MiB instance plus a 2 GB disk is approximately **$7.50/month**, before excess bandwidth. It matches the backend's current SQLite implementation and requires little platform-specific setup. It is a prototype/staging recommendation, not a recommendation for an unrestricted government production service.

There are two material caveats:

1. A Render service with a persistent disk is limited to **one instance** and cannot use zero-downtime deploys. That is acceptable for a single-instance competition rehearsal only if a brief interruption during redeploys is understood and a backup/restore test is completed.
2. A **Johannesburg Fly.io** machine is the closest listed host region geographically to Abuja. It may be worth a short latency test against Render's Frankfurt region before committing. Fly gives more deployment control and local SQLite storage, but puts more responsibility on the team for configuration, backup/restore, monitoring, and recovery. No latency benchmark from Abuja was run for this report.

**Railway Hobby** is a good alternative if the team prefers its developer workflow and is comfortable with metered usage. **DigitalOcean App Platform** is not the lowest-change option: its local filesystem is ephemeral, so this SQLite app would need a database migration or a different persistence design. A future PostgreSQL architecture can be evaluated separately.

This is currently a competition-team prototype, **not a governmental entity or public-sector service**. Government approvals are not a prerequisite for continued feature development or a synthetic-data competition rehearsal. Any future institutional pilot, public-sector deployment, or use of real court data is a separate permission and review question.

## What the current repository needs from a host

- `backend/database.py` uses **SQLite**, with `COURTLOG_DB_PATH` available to select the database file. The database must sit on storage that persists across restarts and deployments. Do not point staging at the repository's tracked `data/courtlog.db`; use a new, empty fictional-data database.
- The application also creates/loads RS256 JWT key files. Set `JWT_PRIVATE_KEY_PATH` and `JWT_PUBLIC_KEY_PATH` on persistent storage, or manage stable keys as deployment secrets. Losing/replacing the key pair invalidates existing sessions/tokens.
- Live mode is the default; it does not seed the demo accounts. Bootstrap a Chief Registrar once through secret environment variables, then remove the bootstrap password from the deployment configuration after verifying the account.
- The frontend is served by the FastAPI application from local, built assets. It does not require a separate Node server at runtime. Use HTTPS so the PWA and secure session cookie work as intended.
- WhatsApp Cloud API sending is **disabled by default**. Hosting alone does not configure Meta, create an approved template, record actual recipient consent, or verify delivery. WhatsApp charges and Meta account eligibility are outside the hosting estimates below.
- The app imports data-science libraries even when the optional trained model artifact is absent. A one-off import of `backend.main` in this workspace used about **80 MiB peak RSS**; this is only a local import measurement, not a hosted load test. Start with 512 MiB and monitor actual memory during the first staging run.

## Provider comparison

| Provider | Closest practical region(s) for Abuja from the published list | Approximate small-instance monthly cost | Persistence fit for the current SQLite app | Main trade-off |
|---|---|---:|---|---|
| **Render** | Frankfurt; Singapore | **$7.50**: $7 512 MiB web service + 2 GB disk at $0.25/GB | Strong fit with a persistent disk | Single-instance disk; no zero-downtime deployment while disk is attached |
| **Railway Hobby** | Amsterdam; Singapore | **About $6.55** in the illustrative low-traffic scenario below; $5/month minimum subscription | Strong fit with a mounted volume | Metered bill can exceed $5; regional volume migration takes downtime |
| **Fly.io** | Johannesburg (`jnb`); also Amsterdam | **About $9.68** using the listed 1 GB machine price, 2 GB volume and 5 GB Africa egress; confirm the JNB-specific compute price | Strong fit with a local volume on one Machine | Most operational control; local volumes do not replicate automatically; Africa egress is higher |
| **DigitalOcean App Platform** | Frankfurt, London, Amsterdam, Singapore among listed regions | **$20**: $5 fixed 512 MiB app + $15 single-node managed PostgreSQL | Not a direct SQLite fit: local storage is ephemeral and App Platform has no persistent volume | Requires a SQLite-to-PostgreSQL migration for durable state; simplest production-oriented database path among these options |

All estimates assume one continuously available web service and a small prototype workload. They exclude tax, custom domains, backups or storage beyond the stated allowance, account-specific promotions, and currency conversion. They are comparison estimates, not provider quotes.

### Render

- The Hobby workspace plan is $0/month and includes 5 GB of bandwidth; the listed 512 MiB / 0.5 CPU service costs $7/month. Persistent SSD storage costs $0.25/GB/month. With a 2 GB disk, the base estimate is **$7.50/month**; bandwidth beyond the included amount is listed at $0.15/GB.
- Render documents regions in Oregon, Ohio, Virginia, Frankfurt, and Singapore. Frankfurt is a reasonable first region to test from Abuja, but actual network latency should be measured from the intended Nigerian mobile/fixed network.
- A persistent disk preserves changes only under its mount path. It is accessible to one service instance, prevents horizontal scaling, and disables zero-downtime deployment. Render's disk documentation also describes disk snapshots; keep an independent backup and practice restoring it rather than treating a provider snapshot as the only backup.
- If memory pressure requires an upgrade, the listed 2 GB RAM / 1 CPU web tier is $25/month. With the same 2 GB disk, that is approximately **$25.50/month** before excess bandwidth.
- Render's managed PostgreSQL starts at $6/month for 256 MiB, with a listed 1 GiB tier at $19/month. The current app has no PostgreSQL adapter, so this is a later migration option rather than a drop-in switch.
- **Free services are not appropriate for persistent SQLite staging:** they spin down after inactivity, use ephemeral filesystems, cannot attach persistent disks, and the free PostgreSQL plan expires after 30 days.

Sources: [Render pricing](https://render.com/pricing), [free-instance limitations](https://render.com/docs/free), [persistent disks and limitations](https://render.com/docs/disks), [available regions](https://render.com/docs/regions).

### Railway

- Hobby costs $5/month and that subscription includes $5 of resource usage. The published resource rates are RAM $10/GB-month, CPU $20/vCPU-month, egress $0.05/GB, and volume storage $0.15/GB-month. If usage exceeds the included $5, the bill rises by the overage; usage below $5 still has the $5 subscription floor.
- A deliberately illustrative scenario—0.5 GB average RAM for a month ($5), 0.05 vCPU average ($1), 5 GB egress ($0.25), and a 2 GB volume ($0.30)—totals **about $6.55/month**. This is not a measured CourtLOG forecast; CPU/RAM and network use should be checked against Railway's usage dashboard.
- Persistent volumes are mounted when the service starts, not during build or pre-deploy. Current documented service regions include US West, US East, Amsterdam, and Singapore. A volume follows its service's region; moving it to another region requires migration and causes downtime.
- The Amsterdam region is a plausible low-latency candidate for Abuja relative to US or Asia, but should be measured from the target network. Railway does not currently list an African deployment region in the region table reviewed.

Sources: [Railway plans and metering](https://docs.railway.com/pricing/plans), [volumes](https://docs.railway.com/volumes), [deployment regions](https://docs.railway.com/deployments/regions).

### Fly.io

- The current pricing page lists shared-cpu-4x / 1 GB at $8.78/month, shared-cpu-2x / 512 MiB at $4.39/month, and 1 GB of RAM at $6/month for other presets. The price selector is region-sensitive: **confirm the current Johannesburg quote in Fly's calculator before choosing a size**.
- Volumes are $0.15/GB-month; snapshots are $0.08/GB-month after the first 10 GB/month free; egress from Africa/India is $0.12/GB. Using the listed $8.78 compute example, a 2 GB volume ($0.30) and 5 GB egress ($0.60) gives an indicative total of **$9.68/month**, before any JNB-specific compute adjustment or optional dedicated IPv4 ($2/month).
- Johannesburg (`jnb`) is in Fly's official application-region list. Fly states that Machines and volumes are tied to regions; volumes attach locally to Machines and do not automatically replicate. The Johannesburg row does not list Fly's Gateway or Managed Postgres availability. A one-Machine SQLite setup is therefore the direct fit, but resilience and off-machine backups need explicit planning.
- Managed Postgres starts at $38/month, before database storage. That is disproportionate for the present competition prototype.

Sources: [Fly.io pricing](https://fly.io/pricing/), [Fly.io regions](https://docs.fly.io/reference/regions), [Fly volumes](https://docs.fly.io/volumes/overview).

### DigitalOcean App Platform

- The fixed shared App Platform container starts at $5/month for 1 vCPU, 512 MiB, and 50 GiB of outbound transfer. Additional outbound transfer is listed at $0.02/GiB.
- App Platform's local filesystem is ephemeral and the platform does not provide persistent volumes. **Do not run the current SQLite database or JWT key files in the container's default writable filesystem as durable state.**
- A single-node managed PostgreSQL plan starts at $15/month. A $5 web container plus that database is approximately **$20/month**. The single-node plan is not high availability; a high-availability PostgreSQL setup starts at a $30/month primary plus at least one matching $30/month standby. The prototype currently needs database-adapter/migration work before it can use PostgreSQL.
- DigitalOcean also lists a 512 MiB development database at $7/month; treat that as a development option, not as the durable database budget used in this comparison. Regional availability varies by product; Frankfurt/London/Amsterdam are candidate regions, and the App Platform region picker should be checked before deployment.

Sources: [App Platform pricing](https://www.digitalocean.com/pricing/app-platform), [App Platform data storage](https://docs.digitalocean.com/products/app-platform/how-to/store-data/), [managed PostgreSQL pricing](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/), [regional availability](https://docs.digitalocean.com/platform/regional-availability/).

## Recommended initial architecture

**For a competition rehearsal with fictional data:**

1. Deploy one paid Render web service in Frankfurt and attach a 2 GB persistent disk at `/var/data`.
2. Set `COURTLOG_DB_PATH=/var/data/courtlog.db`, `JWT_PRIVATE_KEY_PATH=/var/data/private.pem`, and `JWT_PUBLIC_KEY_PATH=/var/data/public.pem`. Verify all three paths are on the mounted disk before accepting any data.
3. Set `DEMO_MODE=false`, `COOKIE_SECURE=true`, and initially `WHATSAPP_ENABLED=false`. Use a fresh database; never copy the tracked repository database into staging. Provide a strong one-time bootstrap administrator through Render's secret environment variables and remove the bootstrap password after verifying the account.
4. Configure a custom domain only if needed; use the host's HTTPS URL during PWA acceptance. Confirm that refresh cookies remain Secure and same-origin.
5. Use fictional records and team-controlled accounts. Before enabling WhatsApp, set up Meta credentials, an approved generic template, stable consent HMAC secret, public webhook subscription, controlled opt-in evidence, and provider callback/opt-out checks. Run this as a separate controlled test; do not treat a `queued` or `accepted` response as delivered.
6. Set an automated, off-host backup cadence for the SQLite file and stable secrets/keys. Rehearse restore to a separate staging database, then verify login, case access, consent lookup, and message status. Provider disk snapshots are useful but are not the only recovery copy.
7. Measure response latency and memory from Abuja, test restart/redeploy persistence, verify the host's health checks/log retention, and document who can access deployment secrets. Do not horizontally scale a single SQLite database.

Illustrative Render commands:

```text
Build:  pip install -r requirements.txt
Start:  uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Run the frontend build in CI or locally when frontend sources change (`npm ci && npm run build:frontend`); the committed static assets are served by the Python app. Use a Python version supported by the pinned requirements (the repository is tested on Python 3.11). Confirm provider build/start syntax and environment-variable handling when creating the service.

## Delivery and decision gates

- **Now through 16 October:** select the host, configure secrets and persistent storage, deploy a fresh fictional-data staging instance, test database/key persistence, and complete a backup/restore rehearsal. Track actual billable usage, not the table estimates.
- **17–20 October:** complete real-device/PWA and login/session acceptance on the intended phone/network, smoke-test restart/redeploy and recovery, and freeze changes for the pilot rehearsal.
- **21 October pilot target:** proceed only with the actual pilot scope agreed by the team. A competition-team rehearsal with fictional data does not imply permission for an institutional deployment or real court records.
- **By 5 November showcase:** use a stable, repeatable staging environment; keep WhatsApp simulation clearly labeled if live Meta setup and controlled delivery acceptance are not complete. A demo must not imply that messages were delivered when they were simulated or merely accepted by the provider.

## Decision summary

- **Best low-change fit:** Render paid service + disk, with one instance and tested off-host backups.
- **Best region to investigate for Abuja:** Fly.io Johannesburg for geography, compared with Render Frankfurt/Railway Amsterdam using measured latency—not a map alone.
- **Best metered alternative:** Railway Hobby, with budget alerts and awareness that actual CPU/RAM usage can exceed the $5 included resource allowance.
- **Best future stateless/PostgreSQL route:** DigitalOcean App Platform plus managed PostgreSQL, after a tested migration; not a direct deploy of the current SQLite code.
- **Not evaluated:** self-managed VPS/Kubernetes and enterprise clouds. They add operational scope beyond this report and are not needed for a small competition rehearsal.

## References checked on 1 October 2026

- Meta Cloud API setup, templates, opt-in, webhooks and pricing are separate from host billing: [Get started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started), [opt-in](https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in), [templates](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview), [webhooks](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview/), [pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing).
- Render: [pricing](https://render.com/pricing), [free services](https://render.com/docs/free), [disks](https://render.com/docs/disks), [regions](https://render.com/docs/regions).
- Railway: [plans/pricing](https://docs.railway.com/pricing/plans), [volumes](https://docs.railway.com/volumes), [regions](https://docs.railway.com/deployments/regions).
- Fly.io: [pricing](https://fly.io/pricing/), [regions](https://docs.fly.io/reference/regions), [volumes](https://docs.fly.io/volumes/overview).
- DigitalOcean: [App Platform pricing](https://www.digitalocean.com/pricing/app-platform), [persistent data guidance](https://docs.digitalocean.com/products/app-platform/how-to/store-data/), [PostgreSQL pricing](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/), [regional availability](https://docs.digitalocean.com/platform/regional-availability/).
