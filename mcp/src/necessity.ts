// Necessity Certificate core logic — TypeScript port of
// skills/necessity-certificate/scripts/necessity_certificate.py, exposed here
// as an MCP tool instead of a CLI. See that file / ../../skills/necessity-certificate/SKILL.md
// for the full methodology this implements.

export type PrivacyCost =
  | "task-relevant, not personal"
  | "quasi-identifier"
  | "direct identifier"
  | "sensitive numeric";

const DIRECT_ID_PATTERN =
  /(name|e_?mail|phone|mobile|ssn|social_security|passport|address|street|iban|account_(id|number)|customer_id|user_id|card_number|credit_card|licen[cs]e|national_id)/i;
const QUASI_ID_PATTERN =
  /(date_of_birth|dob|birth|zip|postal|gender|nationality|city|region|ip_address|device_id|^age$|_age$)/i;
const SENSITIVE_NUMERIC_PATTERN =
  /(salary|income|balance|credit_score|health|diagnosis|amount_owed)/i;

export const DP_TRANSFORM_BY_PRIVACY_COST: Record<PrivacyCost, string> = {
  "task-relevant, not personal": "none",
  "quasi-identifier": "generalize",
  "direct identifier": "pseudonymize",
  "sensitive numeric": "dp_noise",
};

export const STORAGE_TRANSFORM_BY_PRIVACY_COST: Record<PrivacyCost, string> = {
  "task-relevant, not personal": "none",
  "quasi-identifier": "generalize",
  "direct identifier": "encrypt",
  "sensitive numeric": "encrypt",
};

export function classifyPrivacyCost(
  column: string,
  overrides: Record<string, PrivacyCost>
): PrivacyCost {
  if (overrides[column]) return overrides[column];
  if (DIRECT_ID_PATTERN.test(column)) return "direct identifier";
  if (QUASI_ID_PATTERN.test(column)) return "quasi-identifier";
  if (SENSITIVE_NUMERIC_PATTERN.test(column)) return "sensitive numeric";
  return "task-relevant, not personal";
}

export function parseSchema(ddl: string): {
  tableName: string;
  pkColumn: string;
  allColumns: string[];
} {
  const withoutComments = ddl
    .split("\n")
    .filter((line) => !line.trim().startsWith("--"))
    .join("\n");
  const match = withoutComments.match(
    /CREATE\s+TABLE\s+(\w+)\s*\(([\s\S]*)\)\s*;?\s*$/i
  );
  if (!match) {
    throw new Error("Expected exactly one CREATE TABLE statement in schema_sql");
  }
  const [, tableName, body] = match;
  const columns: string[] = [];
  for (const rawLine of body.split("\n")) {
    const line = rawLine.trim().replace(/,$/, "");
    if (!line) continue;
    const upper = line.toUpperCase();
    if (
      upper.startsWith("PRIMARY KEY") ||
      upper.startsWith("FOREIGN KEY") ||
      upper.startsWith("UNIQUE") ||
      upper.startsWith("CHECK")
    ) {
      continue;
    }
    columns.push(line.split(/\s+/)[0]);
  }
  if (columns.length === 0) throw new Error("No columns found in CREATE TABLE statement");
  return { tableName, pkColumn: columns[0], allColumns: columns };
}

// ---------------------------------------------------------------------------
// Declared task execution (LLM-backed, offline majority-class fallback)
// ---------------------------------------------------------------------------

type Record_ = Record<string, unknown>;

function buildPrompt(
  purpose: string,
  labelField: string,
  labelValues: string[] | undefined,
  record: Record_
): string {
  const presentFields = Object.entries(record)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `- ${k}: ${v}`)
    .join("\n");
  const constraint = labelValues
    ? `Reply with exactly one value from this list: ${labelValues.join(", ")}. Reply with the value only, nothing else.`
    : `Reply with your decision for '${labelField}' only, nothing else.`;
  return `You must decide '${labelField}' for the following declared purpose: ${purpose}.\n${constraint}\n\nFields:\n${presentFields}`;
}

async function callOpenAI(
  apiKey: string,
  model: string,
  purpose: string,
  labelField: string,
  labelValues: string[] | undefined,
  record: Record_
): Promise<string> {
  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      temperature: 0,
      messages: [{ role: "user", content: buildPrompt(purpose, labelField, labelValues, record) }],
    }),
  });
  if (!response.ok) {
    throw new Error(`OpenAI call failed: ${response.status} ${await response.text()}`);
  }
  const data = (await response.json()) as {
    choices: { message: { content: string | null } }[];
  };
  const text = (data.choices[0]?.message?.content ?? "").trim();
  if (labelValues) {
    const lower = text.toLowerCase();
    for (const value of labelValues) {
      if (lower.includes(value.toLowerCase())) return value;
    }
  }
  return text;
}

function approxTokenCount(text: string): number {
  // No tiktoken in Workers; word-count approximation, same fallback as the
  // Python script's offline path. Good enough to compare relative payload
  // sizes across ablations, not an exact token count.
  return text.split(/\s+/).filter(Boolean).length;
}

function payload(record: Record_, inputFields: string[], dropField?: string): Record_ {
  const out: Record_ = {};
  for (const field of inputFields) {
    if (field === dropField) continue;
    out[field] = record[field] ?? null;
  }
  return out;
}

function majorityLabel(records: Record_[], labelField: string): string | undefined {
  const counts = new Map<string, number>();
  for (const r of records) {
    const v = r[labelField];
    if (v === undefined || v === null) continue;
    const key = String(v);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  let best: string | undefined;
  let bestCount = -1;
  for (const [k, c] of counts) {
    if (c > bestCount) {
      best = k;
      bestCount = c;
    }
  }
  return best;
}

async function mapWithConcurrency<T, R>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<R>
): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const i = next++;
      results[i] = await fn(items[i], i);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

async function runPass(
  records: Record_[],
  inputFields: string[],
  purpose: string,
  labelField: string,
  labelValues: string[] | undefined,
  model: string,
  useOpenAI: boolean,
  apiKey: string | undefined,
  fallbackMajority: string | undefined,
  dropField?: string
): Promise<{ predictions: string[]; tokensSent: number }> {
  let tokensSent = 0;
  const predictions = await mapWithConcurrency(records, 4, async (record) => {
    const p = payload(record, inputFields, dropField);
    tokensSent += approxTokenCount(JSON.stringify(p));
    if (useOpenAI && apiKey) {
      return callOpenAI(apiKey, model, purpose, labelField, labelValues, p);
    }
    return fallbackMajority ?? "";
  });
  return { predictions, tokensSent };
}

function accuracy(predictions: string[], records: Record_[], labelField: string): number {
  if (records.length === 0) return 0;
  let correct = 0;
  for (let i = 0; i < records.length; i++) {
    if (predictions[i] === String(records[i][labelField] ?? "")) correct++;
  }
  return correct / records.length;
}

export interface EvidenceCard {
  field: string;
  declared_purpose: string;
  privacy_cost: PrivacyCost;
  counterfactual_test: string;
  observed_effect: string;
  accuracy_with_field: string;
  accuracy_without_field: string;
  tokens_saved_per_pass: number;
  operational_action: string;
}

export interface NecessityReport {
  purpose: string;
  table_name: string;
  engine: string;
  test_set_size: number;
  baseline_accuracy: number;
  baseline_tokens_total: number;
  evidence_cards: EvidenceCard[];
  fields_retained: string[];
  fields_blocked: string[];
  example_before_after: { full_payload: Record_; minimized_payload: Record_ };
}

export async function buildReport(opts: {
  purpose: string;
  tableName: string;
  inputFields: string[];
  records: Record_[];
  labelField: string;
  labelValues?: string[];
  privacyCostOverrides: Record<string, PrivacyCost>;
  model: string;
  apiKey?: string;
}): Promise<NecessityReport> {
  const { purpose, tableName, inputFields, records, labelField, labelValues, privacyCostOverrides, model, apiKey } =
    opts;
  const useOpenAI = Boolean(apiKey);
  const fallbackMajority = majorityLabel(records, labelField);
  const n = records.length;

  const baseline = await runPass(
    records,
    inputFields,
    purpose,
    labelField,
    labelValues,
    model,
    useOpenAI,
    apiKey,
    fallbackMajority
  );
  const baselineAccuracy = accuracy(baseline.predictions, records, labelField);

  const evidenceCards: EvidenceCard[] = [];
  const fieldsRetained: string[] = [];

  for (const field of inputFields) {
    const privacyCost = classifyPrivacyCost(field, privacyCostOverrides);
    const ablated = await runPass(
      records,
      inputFields,
      purpose,
      labelField,
      labelValues,
      model,
      useOpenAI,
      apiKey,
      fallbackMajority,
      field
    );
    const ablatedAccuracy = accuracy(ablated.predictions, records, labelField);
    let changed = 0;
    for (let i = 0; i < n; i++) if (baseline.predictions[i] !== ablated.predictions[i]) changed++;
    const degrades = ablatedAccuracy < baselineAccuracy;

    let action: string;
    if (degrades) {
      fieldsRetained.push(field);
      const transform = DP_TRANSFORM_BY_PRIVACY_COST[privacyCost];
      action =
        transform === "none"
          ? "retain: required for task outcome"
          : `retain, but must be '${transform}'-transformed before it may reach the AI view`;
    } else {
      action = "block before the model call";
    }

    evidenceCards.push({
      field,
      declared_purpose: purpose,
      privacy_cost: privacyCost,
      counterfactual_test: `removed in ${n} declared records`,
      observed_effect: `${changed} decisions changed`,
      accuracy_with_field: `${Math.round(baselineAccuracy * 100)}%`,
      accuracy_without_field: `${Math.round(ablatedAccuracy * 100)}%`,
      tokens_saved_per_pass: baseline.tokensSent - ablated.tokensSent,
      operational_action: action,
    });
  }

  const fieldsBlocked = inputFields.filter((f) => !fieldsRetained.includes(f));
  const example = records[0] ?? {};
  const fullPayload = payload(example, inputFields);
  const minimizedPayload: Record_ = {};
  for (const [k, v] of Object.entries(fullPayload)) {
    if (fieldsRetained.includes(k) && DP_TRANSFORM_BY_PRIVACY_COST[classifyPrivacyCost(k, privacyCostOverrides)] === "none") {
      minimizedPayload[k] = v;
    }
  }

  return {
    purpose,
    table_name: tableName,
    engine: useOpenAI ? `openai:${model}` : "offline_majority_class_baseline (dry run only)",
    test_set_size: n,
    baseline_accuracy: baselineAccuracy,
    baseline_tokens_total: baseline.tokensSent,
    evidence_cards: evidenceCards,
    fields_retained: fieldsRetained,
    fields_blocked: fieldsBlocked,
    example_before_after: { full_payload: fullPayload, minimized_payload: minimizedPayload },
  };
}

// ---------------------------------------------------------------------------
// Minimized SQL artifacts
// ---------------------------------------------------------------------------

export function aiViewSql(
  tableName: string,
  pkColumn: string,
  allColumns: string[],
  fieldsRetained: string[],
  privacyCostOverrides: Record<string, PrivacyCost>
): string {
  const lines: string[] = [];
  for (const col of allColumns) {
    if (col === pkColumn || !fieldsRetained.includes(col)) continue;
    const privacyCost = classifyPrivacyCost(col, privacyCostOverrides);
    const transform = DP_TRANSFORM_BY_PRIVACY_COST[privacyCost];
    if (transform === "none") {
      lines.push(col);
    } else {
      lines.push(
        `-- BLOCKED: ${col} is retained but sensitive (${privacyCost}); requires '${transform}' before AI exposure (not yet implemented, fail-closed)`
      );
    }
  }
  const selectedCols = lines.filter((l) => !l.startsWith("--"));
  const header = lines
    .filter((l) => l.startsWith("--"))
    .map((l) => `    ${l}`)
    .join("\n");
  const selectClause =
    `    ${pkColumn}` + (selectedCols.length ? ",\n    " + selectedCols.join(",\n    ") : "");
  return (
    `-- AI-facing view: only necessity-proven, already-safe-to-expose columns\n` +
    `CREATE VIEW ${tableName}_ai_view AS\n` +
    `SELECT\n${selectClause}\nFROM ${tableName};\n` +
    (header ? `${header}\n` : "")
  );
}

export function baseTableSql(
  tableName: string,
  pkColumn: string,
  allColumns: string[],
  fieldsRetained: string[],
  fieldsBlocked: string[],
  privacyCostOverrides: Record<string, PrivacyCost>,
  secondaryRetention: Record<string, string>
): string {
  const lines = [
    "-- Base table: PII columns kept only for a secondary, declared",
    "-- operational purpose are stored transformed, never in plaintext.",
    `CREATE TABLE ${tableName}_secure (`,
    `    ${pkColumn} TEXT PRIMARY KEY,`,
  ];
  const body: string[] = [];
  for (const col of allColumns) {
    if (col === pkColumn) continue;
    const privacyCost = classifyPrivacyCost(col, privacyCostOverrides);
    const transform = STORAGE_TRANSFORM_BY_PRIVACY_COST[privacyCost];

    if (fieldsRetained.includes(col) && transform === "none") {
      body.push(`    ${col} TEXT, -- plaintext: task-relevant, not personal, proven necessary`);
    } else if (secondaryRetention[col]) {
      const purpose = secondaryRetention[col];
      if (transform === "encrypt") {
        body.push(`    ${col}_enc BYTEA, -- pgp_sym_encrypt(${col}, :encryption_key); kept for ${purpose}`);
      } else if (transform === "generalize") {
        body.push(`    ${col}_generalized TEXT, -- generalized from ${col}; kept for ${purpose}`);
      } else {
        body.push(`    ${col}_dp TEXT, -- DP-noised from ${col}; kept for ${purpose}`);
      }
    } else if (fieldsRetained.includes(col)) {
      body.push(
        `    ${col}_enc BYTEA, -- pgp_sym_encrypt(${col}, :encryption_key); proven necessary, pending '${transform}' before AI exposure`
      );
    } else if (fieldsBlocked.includes(col)) {
      body.push(`    -- ${col} dropped entirely: no declared purpose (AI or operational) needs it`);
    }
  }
  for (let i = body.length - 1; i >= 0; i--) {
    if (!body[i].trim().startsWith("--")) {
      body[i] = body[i].includes(", --")
        ? body[i].replace(", --", " --")
        : body[i].replace(/,$/, "");
      break;
    }
  }
  lines.push(...body, ");");
  return lines.join("\n");
}

export interface AuditRow {
  column: string;
  privacy_cost: PrivacyCost;
  necessity: string;
  required_transform: string;
  in_ai_view: boolean;
}

export function dpAudit(
  allColumns: string[],
  pkColumn: string,
  fieldsRetained: string[],
  fieldsBlocked: string[],
  privacyCostOverrides: Record<string, PrivacyCost>,
  secondaryRetention: Record<string, string>
): AuditRow[] {
  const audit: AuditRow[] = [];
  for (const col of allColumns) {
    if (col === pkColumn) continue;
    const privacyCost = classifyPrivacyCost(col, privacyCostOverrides);
    const transform = DP_TRANSFORM_BY_PRIVACY_COST[privacyCost];
    let necessity: string;
    let inAiView: boolean;
    if (fieldsRetained.includes(col)) {
      necessity = "proven necessary for the declared AI task";
      inAiView = transform === "none";
    } else if (secondaryRetention[col]) {
      necessity = `not needed by the AI task; retained for ${secondaryRetention[col]}`;
      inAiView = false;
    } else if (fieldsBlocked.includes(col)) {
      necessity = "not needed by the AI task; no other declared purpose";
      inAiView = false;
    } else {
      necessity = "never covered by the necessity test; fail-closed, treated as unnecessary";
      inAiView = false;
    }
    audit.push({ column: col, privacy_cost: privacyCost, necessity, required_transform: transform, in_ai_view: inAiView });
  }
  return audit;
}

export function renderMarkdown(report: NecessityReport, audit: AuditRow[]): string {
  const lines: string[] = [
    "# Necessity Certificate",
    "",
    `**Declared purpose:** ${report.purpose}`,
    `**Engine:** ${report.engine}`,
    `**Test set size:** ${report.test_set_size}`,
    `**Baseline accuracy:** ${Math.round(report.baseline_accuracy * 100)}%`,
    "",
    "## Evidence cards",
    "",
  ];
  for (const card of report.evidence_cards) {
    lines.push(
      `### \`${card.field}\``,
      "```text",
      `Source field: ${card.field}`,
      `Declared purpose: ${card.declared_purpose}`,
      `Privacy cost: ${card.privacy_cost}`,
      `Counterfactual test: ${card.counterfactual_test}`,
      `Observed effect: ${card.observed_effect} (accuracy ${card.accuracy_with_field} -> ${card.accuracy_without_field})`,
      `Tokens saved per pass if blocked: ${card.tokens_saved_per_pass}`,
      `Operational action: ${card.operational_action}`,
      "```",
      ""
    );
  }
  lines.push(
    "## Column disposition (fail-closed by default)",
    "",
    "| column | privacy cost | necessity | required transform | in AI view |",
    "|---|---|---|---|---|"
  );
  for (const row of audit) {
    lines.push(`| ${row.column} | ${row.privacy_cost} | ${row.necessity} | ${row.required_transform} | ${row.in_ai_view} |`);
  }
  lines.push(
    "",
    `**Fields retained (proven necessary):** ${JSON.stringify(report.fields_retained)}`,
    `**Fields blocked before the model call:** ${JSON.stringify(report.fields_blocked)}`,
    "",
    "## Limits",
    "",
    "This is empirical evidence for the declared purpose, model, prompt, and test set shown above -- not a " +
      "universal legal or mathematical proof. A different task, prompt, model version, or field interaction can " +
      "change the result. Treat this as input to a DPIA or engineering review, not a legal verdict."
  );
  return lines.join("\n");
}
