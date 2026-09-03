-- Real-world base table: it always has more columns than any single
-- declared AI task actually needs. support_notes is a free-text column
-- that was never covered by the ticket-routing necessity test (see
-- poc/minimize.py / poc/report.json) and must therefore be treated as
-- unproven -> blocked by default (fail-closed), exactly like a field
-- that was tested and found unnecessary.
CREATE TABLE support_tickets (
    id              TEXT PRIMARY KEY,
    issue_description TEXT,
    product_area    TEXT,
    urgency         TEXT,
    name            TEXT,
    email           TEXT,
    phone           TEXT,
    date_of_birth   DATE,
    address         TEXT,
    account_id      TEXT,
    support_notes   TEXT,
    expected_queue  TEXT
);
