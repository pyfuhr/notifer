# /tostpool notify server
This service is a simple FastAPI backend for delivering push notifications from companies to their subscribers. It uses a hybrid storage architecture: SQLite handles persistent data (user/company accounts, password hashes, and subscription pairs), while Redis acts as a fast, temporary buffer for the messages.

The core logic operates as a single-read queue. When a company posts an update, it is pushed to the user's specific Redis list with a 24-hour TTL to prevent memory bloat. When the user requests /notifies, the backend uses a Redis pipeline to atomically fetch all pending messages and instantly delete the key, ensuring exact-once delivery with zero duplicates and minimal disk overhead.

## Usage
```bash
git clone https://github.com/pyfuhr/notifer
cd notifer
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 39080
```
## Endpoint
### Users (/user)

* POST /user/register — Sign up
* Request: {"name": "str", "password": "str"}
   * Response (200): {"token": "str"} | 409 (already exists)
* POST /user/auth — Log in (To be more precise, it's a token renew)
* Request: {"name": "str", "password": "str"}
   * Response (200): {"token": "str"} | 404 (not found) | 401 (wrong password)

### Companies (/company)

* POST /company/register — Register company
* Request: {"name": "str", "password": "str"}
   * Response (200): {"token": "str"} | 409 (already exists)
* POST /company/auth — Log in company (To be more precise, it's a token renew)
* Request: {"name": "str", "password": "str"}
   * Response (200): {"token": "str"} | 404 (not found) | 401 (wrong password)

### Subscriptions & Notifications

* POST /subscribe/{cname} — Subscribe to company (cname (company name) in URL)
* Request: {"token": "str"} (user token)
   * Response (200): {"subscribe_id": "str"} | 404 (no company) | 401 (invalid token)
* POST /publish — Publish news to Redis (update TTL to all other post to that user)
* Request: {"ctoken": "str", "stoken": "str", "data": "str"}
   * Response (204): Empty body | 401 (invalid ctoken) | 404 (invalid stoken)
* GET /notifies — Read and clear notifications from Redis
* Request: {"token": "str"} (user token)
   * Response (200): [{"company": "str", "data": "str", "dt": float}, ...] | 401 (invalid token)
