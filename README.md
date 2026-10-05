# Order Tracker

A small order tracking app for the AI Dev Tools Zoomcamp observability homework. It includes a web page, API, tests, and a Docker Compose setup. You add telemetry, alerts, and an incident responder in Homework 4.

The main user flow is creating an order and checking its status. Three sample orders are created on first startup.

## Run it

You need Docker with Compose. To run the tests, you also need Python 3.11+ and `uv`.

```bash
docker compose up --build -d --wait
```

Open <http://127.0.0.1:8000> for the app and <http://127.0.0.1:3000> for Grafana. Grafana credentials are `admin` / `admin`. The provisioned Order Tracker dashboard and 5xx alert use Prometheus, fed by the local OpenTelemetry Collector. Data is stored in Docker volumes and survives container recreation.

If port 8000 is occupied, set `ORDER_TRACKER_PORT`, for example:

```bash
ORDER_TRACKER_PORT=18080 docker compose up --build -d --wait
```

The order lookup endpoint emits OpenTelemetry server spans, completion logs,
and an `order_lookup_requests` counter labeled with `http.route` and
`http.response.status_code`. By default, Compose exports metrics to the local
collector. The Grafana alert evaluates 5xx responses for
`GET /api/orders/{order_id}` over 5 minutes, with a 1-minute pending period;
missing 5xx data is treated as normal. To send spans or logs to another
collector, configure the corresponding OTLP endpoint variables.

Run tests with `uv run --frozen pytest -q`. Stop the app with `docker compose down`. Add `-v` only if you also want to delete the order data.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Web page |
| GET | `/healthz` | Database health check |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Create an order |
| GET | `/api/orders/{id}` | Check an order |
| PATCH | `/api/orders/{id}` | Change an order status |

The app uses SQLite to keep setup small. Run one app container at a time. The course exercise is about detecting and handling an incident, not scaling the database.
