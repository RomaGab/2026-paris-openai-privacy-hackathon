import assert from "node:assert/strict";
import test from "node:test";

import { aiViewSql, buildReport, shouldRetainField } from "../src/necessity.ts";

test("offline engine measures repeated task signal", async () => {
  const records = [
    { id: "1", signal: "billing invoice", email: "a@example.com", label: "billing" },
    { id: "2", signal: "billing invoice", email: "b@example.com", label: "billing" },
    { id: "3", signal: "login password", email: "c@example.com", label: "security" },
    { id: "4", signal: "login password", email: "d@example.com", label: "security" },
  ];

  const report = await buildReport({
    purpose: "route a support request",
    tableName: "tickets",
    inputFields: ["signal", "email"],
    records,
    labelField: "label",
    labelValues: ["billing", "security"],
    privacyCostOverrides: {},
    model: "gpt-4o-mini",
  });

  assert.equal(report.baseline_accuracy, 1);
  assert.deepEqual(report.fields_retained, ["signal"]);
  assert.deepEqual(report.fields_blocked, ["email"]);
});

test("AI view does not expose the untested primary key", () => {
  const sql = aiViewSql(
    "tickets",
    "account_id",
    ["account_id", "signal", "email"],
    ["signal"],
    {}
  );

  const selectBlock = sql.split("FROM", 1)[0];
  assert.match(selectBlock, /signal/);
  assert.doesNotMatch(selectBlock, /account_id/);
});

test("any changed decision prevents automatic blocking", () => {
  assert.equal(shouldRetainField(1), true);
  assert.equal(shouldRetainField(0), false);
});
