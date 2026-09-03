import { McpServer } from "@modelcontextprotocol/server";
import { createMcpHandler } from "agents/mcp/server";
import { z } from "zod";
import {
  aiViewSql,
  baseTableSql,
  buildReport,
  classifyPrivacyCost,
  dpAudit,
  parseSchema,
  renderMarkdown,
  type PrivacyCost,
} from "./necessity";

export interface Env {
  OPENAI_API_KEY?: string;
}

const PRIVACY_COST_ENUM = z.enum([
  "task-relevant, not personal",
  "quasi-identifier",
  "direct identifier",
  "sensitive numeric",
]);

const MAX_RECORDS = 25;

function createServer(env: Env) {
  const server = new McpServer({ name: "necessity-certificate", version: "0.1.0" });

  server.registerTool(
    "classify_columns",
    {
      description:
        "Classify every column of a SQL CREATE TABLE statement into a privacy-cost category " +
        "(task-relevant not personal / quasi-identifier / direct identifier / sensitive numeric), " +
        "using a name-based heuristic. Review and override before trusting it for anything sensitive.",
      inputSchema: {
        schema_sql: z.string().describe("A single CREATE TABLE ... statement."),
        privacy_cost_overrides: z
          .record(z.string(), PRIVACY_COST_ENUM)
          .optional()
          .describe("Column name -> privacy cost category, overriding the heuristic."),
      },
    },
    async ({ schema_sql, privacy_cost_overrides }) => {
      const { tableName, pkColumn, allColumns } = parseSchema(schema_sql);
      const overrides = (privacy_cost_overrides ?? {}) as Record<string, PrivacyCost>;
      const classification = allColumns
        .filter((c) => c !== pkColumn)
        .map((c) => ({ column: c, privacy_cost: classifyPrivacyCost(c, overrides) }));
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({ table_name: tableName, primary_key: pkColumn, columns: classification }, null, 2),
          },
        ],
      };
    }
  );

  server.registerTool(
    "necessity_certificate",
    {
      description:
        "Turn a declared AI use case + a database schema + a labeled dataset into a Necessity Certificate: " +
        "for every column, run a counterfactual test (baseline vs. removing that column) to measure whether it " +
        "actually changes the declared task's outcome, then emit a per-field justification, a minimized " +
        "AI-facing SQL view (only proven-necessary, safe-to-expose columns), and a secure base-table DDL " +
        "(columns kept only for a secondary declared purpose are stored encrypted/generalized, never plain). " +
        "Fail-closed: any column not proven necessary is blocked by default. " +
        "Set the OPENAI_API_KEY secret on this Worker to get real evidence; without it, this falls back to an " +
        "offline majority-class dry run that only exercises the pipeline, not genuine evidence.",
      inputSchema: {
        purpose: z.string().describe("Declared purpose of the AI task, in plain language, e.g. 'route a support ticket to the right queue'."),
        schema_sql: z.string().describe("A single CREATE TABLE ... statement for the table in question."),
        records: z
          .array(z.record(z.string(), z.any()))
          .min(1)
          .max(MAX_RECORDS)
          .describe(`Labeled records (JSON objects), max ${MAX_RECORDS} for this demo deployment. Each must include the label_field with its ground-truth value.`),
        label_field: z.string().describe("Column holding the expected/ground-truth decision for each record."),
        label_values: z
          .array(z.string())
          .optional()
          .describe("Allowed decision values, if the task is a classification."),
        privacy_cost_overrides: z
          .record(z.string(), PRIVACY_COST_ENUM)
          .optional()
          .describe("Column name -> privacy cost category, overriding the name-based heuristic."),
        secondary_retention: z
          .record(z.string(), z.string())
          .optional()
          .describe("Column name -> declared non-AI reason to keep it in storage (e.g. 'support agent lookup'). Columns not listed here are dropped entirely if blocked from the AI view."),
        model: z.string().optional().default("gpt-4o-mini").describe("OpenAI chat model to use for the counterfactual test."),
      },
    },
    async ({ purpose, schema_sql, records, label_field, label_values, privacy_cost_overrides, secondary_retention, model }) => {
      const { tableName, pkColumn, allColumns } = parseSchema(schema_sql);
      const inputFields = allColumns.filter((c) => c !== pkColumn && c !== label_field);
      const overrides = (privacy_cost_overrides ?? {}) as Record<string, PrivacyCost>;
      const secondary = secondary_retention ?? {};

      const report = await buildReport({
        purpose,
        tableName,
        inputFields,
        records: records as Record<string, unknown>[],
        labelField: label_field,
        labelValues: label_values,
        privacyCostOverrides: overrides,
        model: model ?? "gpt-4o-mini",
        apiKey: env.OPENAI_API_KEY,
      });

      const audit = dpAudit(allColumns, pkColumn, report.fields_retained, report.fields_blocked, overrides, secondary);
      const view = aiViewSql(tableName, pkColumn, allColumns, report.fields_retained, overrides);
      const table = baseTableSql(tableName, pkColumn, allColumns, report.fields_retained, report.fields_blocked, overrides, secondary);
      const markdown = renderMarkdown(report, audit);

      return {
        content: [
          { type: "text", text: markdown },
          { type: "text", text: `${view}\n\n${table}` },
          { type: "text", text: JSON.stringify(report, null, 2) },
        ],
      };
    }
  );

  return server;
}

const handler = {
  fetch(request: Request, env: Env, ctx: ExecutionContext) {
    return createMcpHandler(() => createServer(env))(request, env, ctx);
  },
};

export default handler satisfies ExportedHandler<Env>;
