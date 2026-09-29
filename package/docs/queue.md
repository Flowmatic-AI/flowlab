# Queue

Background jobs: dispatch from a route, a tool or a command, and run them in a worker with the full app.

```python
from flowlab.modules.queue import job


@job(queue="emails", tries=3, backoff=[10, 60])
def send_welcome(user_id: int) -> None: ...


send_welcome.dispatch(user.id)     # queue it; returns the job id
send_welcome.later(60, user.id)    # queue it to run in a minute
send_welcome(user.id)              # run it now, in this process
```

```bash
python main.py queue:work --queue emails,default
```

## Jobs

`@job` (or `@job(queue=..., tries=..., backoff=...)`) turns a module-level function into a `Job`:

- `queue`: the queue it goes to. Defaults to `QUEUE_NAME`.
- `tries`: how many times a worker runs it before it counts as failed. Defaults to 1.
- `backoff`: seconds to wait before each retry, one number or one per retry (`[10, 60]` waits 10 seconds, then 60
  for every later retry). Defaults to 0.

`dispatch(*args, **kwargs)` and `later(delay, *args, **kwargs)` are typed like the function, and check the arguments
against its signature before queueing. Arguments are stored as JSON, so they must be JSON serializable: pass ids, not
models. A worker finds a job by its import path (`app.jobs.welcome:welcome_user`), so jobs must live at module level
in a module the worker can import (`app/jobs/` in the starter). Only `@job` functions resolve: a payload naming any
other callable fails without running. Async functions work too.

## Drivers

`QUEUE_DRIVER` picks where jobs wait:

| Driver | Needs | Notes |
| --- | --- | --- |
| `sync` (default) | nothing | Runs each job the moment it is dispatched, in the dispatching process. Exceptions reach the caller; `tries`, `backoff` and delays are ignored. For tests and local development. |
| `database` | the `jobs` and `failed_jobs` tables (`queue:install`, then `migrations:up`) | Any database flowlab supports. |
| `redis` / `valkey` | `flowlab[redis]` / `flowlab[valkey]` | Keys start with `flowlab:queue`. |
| `cloudtasks` | `flowlab[gcp]`, the `failed_jobs` table | Google Cloud Tasks calls the app over HTTP to run each job, so nothing polls and a Cloud Run service can scale to zero. See [Cloud Tasks](#cloud-tasks). |

| Env var | Default | Meaning |
| --- | --- | --- |
| `QUEUE_DRIVER` | `sync` | `sync`, `database`, `redis`, `valkey` or `cloudtasks` |
| `QUEUE_NAME` | `default` | the queue for jobs that don't name one, and the one `queue:work` works by default |
| `QUEUE_RETRY_AFTER` | `90` | seconds before a job whose worker died is handed out again |
| `QUEUE_MAX_IDLE` | none | seconds of empty queues after which `queue:work` stops; `--max-idle` overrides it |
| `QUEUE_HOST`, `QUEUE_PORT`, `QUEUE_DB`, `QUEUE_PASSWORD` | `localhost`, `6379`, `0`, none | Redis or Valkey connection |
| `QUEUE_GCP_PROJECT`, `QUEUE_GCP_LOCATION` | none | Cloud Tasks: the project and region of the queues |
| `QUEUE_TARGET_URL` | none | Cloud Tasks: base URL of the service that runs jobs, `https://worker-abc.a.run.app` |
| `QUEUE_SERVICE_ACCOUNT` | none | Cloud Tasks: the service account whose OIDC token the tasks carry |
| `QUEUE_PUSH_PATH` | `/_flowlab/queue` | Cloud Tasks: the route that runs pushed jobs |

With the `database` driver, the server refuses to start with `SchemaMismatch` while the tables are missing, as the auth
module does.

## Workers

`queue:work` takes jobs off the queues and runs them inside the app's lifespan, so `get_db()`, `get_cache()` and
`get_app()` work in a job.

```
queue:work [--queue high,default] [--once] [--stop-when-empty] [--max-idle SECONDS] [--max-jobs N] [--sleep 3]
           [--log-level INFO]
```

- `--queue` lists queues in priority order: a job on `high` always goes before one on `default`.
- A job that raises is put back after its `backoff` until it has run `tries` times, then moves to the failed jobs,
  with its traceback.
- Ctrl+C or SIGTERM lets the current job finish, then the worker stops. On Cloud Run the instance is killed about
  10 seconds after SIGTERM, so a longer job is cut off and runs again after `QUEUE_RETRY_AFTER`.
- `--max-idle 60` (or `QUEUE_MAX_IDLE=60`) stops the worker once the queues have been empty for a minute, for a
  worker started on demand (a Cloud Run Job run by Cloud Scheduler, say) that should not keep billing while there is
  nothing to do.
- Every attempt is logged: `2026-09-29 14:26:16 DONE  app.jobs.welcome:welcome_user [8abdd932] 1ms`.
- Jobs can log: the worker sets up Python logging at `--log-level` (default `INFO`) unless the app already has, so a
  job's `logging.getLogger(__name__).info(...)` shows next to those lines.
- Run as many workers as you like: each job goes to exactly one of them. If a worker dies mid-job, the job becomes
  available again after `QUEUE_RETRY_AFTER` seconds and counts as an attempt. A job that runs longer than that can
  be picked up by a second worker, so keep `QUEUE_RETRY_AFTER` above your slowest job.

A worker only picks up code changes when restarted.

## Cloud Tasks

A polling worker is billed for every second it runs, empty queue or not, and Cloud Run only gives it CPU with
instance-based billing. With `QUEUE_DRIVER=cloudtasks` nothing polls: dispatching a job creates a
[Cloud Task](https://cloud.google.com/tasks/docs) that POSTs it to `QUEUE_TARGET_URL` + `QUEUE_PUSH_PATH`, and the app
runs it there, inside its lifespan, like a worker would. Cloud Run starts instances when tasks arrive and scales back to
zero after, so you pay while jobs run. There is no `queue:work`.

```
QUEUE_DRIVER=cloudtasks
QUEUE_GCP_PROJECT=my-project
QUEUE_GCP_LOCATION=europe-west1
QUEUE_TARGET_URL=https://worker-abc.a.run.app
QUEUE_SERVICE_ACCOUNT=tasks@my-project.iam.gserviceaccount.com
```

Set up once per project:

```bash
gcloud tasks queues create default --location=europe-west1 --max-attempts=5   # one per flowlab queue name
gcloud iam service-accounts create tasks
gcloud run services add-iam-policy-binding worker --member=serviceAccount:tasks@my-project.iam.gserviceaccount.com \
    --role=roles/run.invoker --region=europe-west1
# whoever dispatches jobs needs roles/cloudtasks.enqueuer, and roles/iam.serviceAccountUser on the tasks account
```

- Each flowlab queue is the Cloud Tasks queue of the same name, so queue names must be valid Cloud Tasks queue ids.
  Priority between queues comes from each queue's rate limits (`--max-dispatches-per-second`,
  `--max-concurrent-dispatches`), not from an order.
- The route only runs requests carrying a Google-signed OIDC token for `QUEUE_TARGET_URL`, issued to
  `QUEUE_SERVICE_ACCOUNT`. It can live on your API service or on a separate `worker` service with the same code; the
  API and the worker both need the settings above.
- `tries` and `backoff` work as with a worker: a job that raised is scheduled again as a new task after its backoff,
  and after its last try it goes to `failed_jobs` (so run `queue:install` and `migrations:up`), where `queue:failed`
  and `queue:retry` find it. The route answers 2xx for all of these.
- When the app itself fails (5xx) or doesn't answer within `QUEUE_RETRY_AFTER` seconds (clamped to Cloud Tasks'
  15 seconds to 30 minutes), Cloud Tasks retries the same task using the queue's retry config, and each retry counts as
  an attempt. A job still failing that way when the queue's `--max-attempts` runs out is dropped by Cloud Tasks without
  reaching `failed_jobs`.
- Delivery is at least once: keep jobs safe to run twice. A payload can be at most 1 MB, and a job at most 30 minutes.
- Sync jobs run in the server's thread pool. Set the Cloud Run service's `--concurrency` to how many jobs one instance
  can run at once, and its request timeout above your slowest job.
- `queue.size()` counts by listing every task, so it is slow on a long queue; `queue.clear()` purges the Cloud Tasks
  queue.

## Failed jobs

```
queue:failed               # id, time, queue, job and the exception, most recent first
queue:retry <id>... | all  # put failed jobs back on their queue, attempts counted from zero
queue:forget <id>          # delete one failed job
queue:flush                # delete every failed job
queue:clear [--queue q] [--force]  # delete every job still waiting on a queue
```

## Without the CLI

The app's queue is `get_queue()` (or `app.queue`), a `Queue`:

```python
queue.push("app.jobs.welcome:welcome_user", [1], queue="emails", delay=60)
queue.size("emails")
queue.failed(); queue.retry(id); queue.forget(id); queue.flush(); queue.clear("emails")
```

`Queue.sync()`, `Queue.connect_database(db)`, `Queue.connect_redis(...)`, `Queue.connect_valkey(...)` and
`Queue.connect_cloud_tasks(db, project, location, url, service_account)` build one
outside an app. `Worker(queue, ["emails"], stop_when_empty=True).run()` works it in-process, which is handy in tests.

## How it works

- **database:** reserving a job is a compare-and-set on its `reservation` column, and moves its `available_at` to when
  the reservation runs out. One condition, `available_at <= now`, then finds both due jobs and jobs whose worker
  died. There are no row locks, so it behaves the same on SQLite, PostgreSQL, MySQL and MariaDB.
- **redis / valkey:** each queue is a list plus sorted sets of delayed and reserved jobs. A Lua script moves due jobs
  onto the list, pops one and records its reservation in one atomic step.
- **cloudtasks:** Cloud Tasks holds the waiting and delayed jobs. A retry is a new task carrying the attempts so far in
  an `X-Flowlab-Attempts` header, added to Cloud Tasks' own `X-CloudTasks-TaskRetryCount`.

## Public API

`job`, `Job`, `Queue`, `Worker`, `ReservedJob`, `FailedJob`, `JobNotFound`, `resolve`, `module`, `MIGRATIONS_DIR`;
adapters in `flowlab.modules.queue.adapters`. From `flowlab`: `QueueSettings`, `QueueDriver`, `get_queue`.
