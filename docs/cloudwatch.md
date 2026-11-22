# CloudWatch logs

The backend sends JSON logs to `<CLOUDWATCH_LOG_GROUP_PREFIX>/<APP_ENV>/backend` and receives desktop log labels at `POST /logs`, forwarding them to the corresponding `/frontend` group. Sentry continues to handle errors, tracing, and replay; its structured log delivery is disabled in both projects.

Set these backend environment variables:

```dotenv
CLOUDWATCH_ENABLED=true
CLOUDWATCH_REGION=us-east-1
CLOUDWATCH_LOG_GROUP_PREFIX=/yoink
APP_ENV=production
```

The backend uses Boto3's normal AWS credential chain. Use an IAM role in production and an AWS profile for local development. Never distribute AWS credentials in the desktop application. The backend creates the groups if missing and sets 30-day retention. Grant its role `logs:CreateLogGroup`, `logs:PutRetentionPolicy`, `logs:CreateLogStream`, and `logs:PutLogEvents` for the configured groups, plus `logs:DescribeLogGroups` for group discovery. Provision groups separately and remove automatic group creation from the handler if your infrastructure manages retention instead.

The frontend's existing `YOINK_BACKEND_URL` must point to this backend when the app is built. Logs are batched in the background, with a 200-event queue, 20-event batches, request timeouts, and at most three attempts per failing batch. Local file/console logging continues. Shutdown delivery is best effort and never requires users to configure AWS.

`POST /logs` is intentionally a public, write-only telemetry endpoint; it does not authenticate desktop installations. It accepts only predefined labels and severity, rejects extra fields, limits requests to 16 KiB and 20 events, and applies per-worker limits of 60 batches per source address and 300 batches globally per minute. It never accepts AWS destinations or arbitrary log content. Counter memory is bounded and expires every minute. If deployed behind a proxy or across workers, apply aggregate rate limits at the ingress too; the application does not trust forwarded IP headers.

Allowlisted labels, rather than URLs, error objects, account details, or provider payloads, leave the desktop. Backend logs retain their existing structured fields. AWS SDK delivery diagnostics are excluded from CloudWatch forwarding to prevent logging loops. Queued server logs flush on application shutdown.

For verification, start the backend, call `/health`, and submit:

```sh
curl -H 'Content-Type: application/json' \
  --data '{"events":[{"level":"info","message":"Application log"}]}' \
  http://127.0.0.1:8000/logs
```

Expect HTTP 202, then check the frontend log group after the five-second delivery interval. A disabled relay returns HTTP 503; rate limits return HTTP 429 with a retry hint. A 202 response acknowledges the queue, not durable AWS receipt. Logging failures should not be treated as successful delivery until events are visible in CloudWatch.
