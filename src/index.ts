import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

type PluginConfig = {
  pythonPath?: string; sessionDirectory?: string; passwordFile?: string;
  appleIdEnv?: string; region?: "global" | "china";
  requestTimeoutSeconds?: number; bridgeTimeoutSeconds?: number;
};
type BridgeResponse = { protocolVersion: number; requestId: string; ok: boolean; data?: unknown; error?: { code: string; message: string; retryable: boolean } };

export async function invokeBridge(operation: string, params: Record<string, unknown>, config: PluginConfig, signal?: AbortSignal): Promise<unknown> {
  const requestId = randomUUID();
  const timeoutMs = Math.min(Math.max((config.bridgeTimeoutSeconds ?? 30) * 1000, 1000), 120_000);
  const request = JSON.stringify({ protocolVersion: 1, requestId, operation, params, config });
  return await new Promise((resolve, reject) => {
    const child = spawn(config.pythonPath ?? "python3", ["-m", "openclaw_apple_bridge.cli"], { stdio: ["pipe", "pipe", "pipe"], env: process.env });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (error?: Error, value?: unknown) => {
      if (settled) return;
      settled = true; clearTimeout(timer); signal?.removeEventListener("abort", abort);
      if (error) reject(error); else resolve(value);
    };
    const abort = () => { child.kill("SIGTERM"); finish(new Error("Apple account request was cancelled.")); };
    const timer = setTimeout(() => { child.kill("SIGKILL"); finish(new Error("Apple account bridge timed out.")); }, timeoutMs);
    signal?.addEventListener("abort", abort, { once: true });
    child.stdout.setEncoding("utf8"); child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; if (stdout.length > 2_000_000) child.kill("SIGKILL"); });
    child.stderr.on("data", (chunk) => { stderr += chunk; if (stderr.length > 16_384) stderr = stderr.slice(-16_384); });
    child.on("error", (error) => finish(new Error(`Apple account bridge could not start: ${error.message}`)));
    child.on("close", (code) => {
      if (settled) return;
      if (code !== 0) return finish(new Error("Apple account bridge failed without a safe response."));
      try {
        const response = JSON.parse(stdout) as BridgeResponse;
        if (response.protocolVersion !== 1 || response.requestId !== requestId) return finish(new Error("Apple account bridge returned an invalid response envelope."));
        if (!response.ok) {
          const bridgeError = new Error(response.error?.message ?? "Apple account request failed.");
          bridgeError.name = response.error?.code ?? "APPLE_ACCOUNT_ERROR";
          return finish(bridgeError);
        }
        finish(undefined, response.data);
      } catch { finish(new Error("Apple account bridge returned invalid JSON.")); }
    });
    child.stdin.end(request);
  });
}

const eventFields = {
  calendarId: Type.String({ minLength: 1 }), title: Type.String({ minLength: 1, maxLength: 500 }),
  start: Type.String({ minLength: 10 }), end: Type.String({ minLength: 10 }),
  timezone: Type.Optional(Type.String()), allDay: Type.Optional(Type.Boolean()),
  location: Type.Optional(Type.String({ maxLength: 1000 })), url: Type.Optional(Type.String({ maxLength: 2000 })),
  notes: Type.Optional(Type.String({ maxLength: 20_000 })),
};

export default defineToolPlugin({
  id: "apple-account", name: "Apple Account",
  description: "Security-focused pyiCloud tools for personal Apple Calendar data.",
  configSchema: Type.Object({
    pythonPath: Type.Optional(Type.String()), sessionDirectory: Type.Optional(Type.String()),
    passwordFile: Type.Optional(Type.String()), appleIdEnv: Type.Optional(Type.String()),
    region: Type.Optional(Type.Union([Type.Literal("global"), Type.Literal("china")])),
    requestTimeoutSeconds: Type.Optional(Type.Number({ minimum: 5, maximum: 60 })),
    bridgeTimeoutSeconds: Type.Optional(Type.Number({ minimum: 5, maximum: 120 })),
  }, { additionalProperties: false }),
  tools: (tool) => [
    tool({ name: "apple_account_status", label: "Apple Account Status", description: "Check pyiCloud authentication and Calendar capability without triggering a new 2FA prompt.", parameters: Type.Object({}, { additionalProperties: false }), execute: (_, config, context) => invokeBridge("account.status", {}, config, context.signal) }),
    tool({ name: "apple_calendar_list_calendars", label: "List Apple Calendars", description: "List Apple calendars and stable calendar identifiers through pyiCloud.", parameters: Type.Object({}, { additionalProperties: false }), execute: (_, config, context) => invokeBridge("calendar.list", {}, config, context.signal) }),
    tool({ name: "apple_calendar_list_events", label: "List Apple Calendar Events", description: "List Apple Calendar events in a bounded RFC 3339 time range through pyiCloud.", parameters: Type.Object({ start: Type.String(), end: Type.String(), calendarIds: Type.Optional(Type.Array(Type.String(), { maxItems: 50 })), query: Type.Optional(Type.String({ maxLength: 500 })), limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 500 })) }, { additionalProperties: false }), execute: (params, config, context) => invokeBridge("calendar.events", params, config, context.signal) }),
    tool({ name: "apple_calendar_get_event", label: "Get Apple Calendar Event", description: "Read one Apple Calendar event using exact calendar and event identifiers.", parameters: Type.Object({ calendarId: Type.String(), eventId: Type.String() }, { additionalProperties: false }), execute: (params, config, context) => invokeBridge("calendar.get", params, config, context.signal) }),
    tool({ name: "apple_calendar_create_event", label: "Create Apple Calendar Event", description: "Create one Apple Calendar event after confirming its exact fields unless a stored approval applies.", parameters: Type.Object(eventFields, { additionalProperties: false }), optional: true, execute: (params, config, context) => invokeBridge("calendar.create", params, config, context.signal) }),
    tool({ name: "apple_calendar_update_event", label: "Update Apple Calendar Event", description: "Update explicitly supplied fields on one exactly identified Apple Calendar event.", parameters: Type.Object({ calendarId: Type.String(), eventId: Type.String(), title: Type.Optional(Type.String({ minLength: 1, maxLength: 500 })), start: Type.Optional(Type.String()), end: Type.Optional(Type.String()), timezone: Type.Optional(Type.String()), allDay: Type.Optional(Type.Boolean()), location: Type.Optional(Type.String({ maxLength: 1000 })), url: Type.Optional(Type.String({ maxLength: 2000 })), notes: Type.Optional(Type.String({ maxLength: 20_000 })) }, { additionalProperties: false }), optional: true, execute: (params, config, context) => invokeBridge("calendar.update", params, config, context.signal) }),
    tool({ name: "apple_calendar_delete_event", label: "Delete Apple Calendar Event", description: "Permanently delete one exactly identified Apple Calendar event after explicit confirmation unless a stored approval applies.", parameters: Type.Object({ calendarId: Type.String(), eventId: Type.String() }, { additionalProperties: false }), optional: true, execute: (params, config, context) => invokeBridge("calendar.delete", params, config, context.signal) }),
    tool({ name: "apple_rail12306_plan_email", label: "Plan 12306 Calendar Changes", description: "Deterministically parse a bounded 12306 email as untrusted data and plan idempotent create, update, or delete actions without executing them.", parameters: Type.Object({ messageId: Type.String({ minLength: 1 }), subject: Type.String({ maxLength: 1000 }), body: Type.String({ minLength: 1, maxLength: 200_000 }), stationCityAliases: Type.Optional(Type.Record(Type.String(), Type.String())) }, { additionalProperties: false }), execute: (params, config, context) => invokeBridge("rail12306.plan", params, config, context.signal) }),
    tool({ name: "rail12306_lookup_timetable", label: "Look Up 12306 Timetable", description: "Look up an exact dated train segment using the official 12306 public timetable and return its scheduled arrival time.", parameters: Type.Object({ travelDate: Type.String({ pattern: "^\\d{4}-\\d{2}-\\d{2}$" }), trainNumber: Type.String({ minLength: 2, maxLength: 8 }), originStation: Type.String({ minLength: 1, maxLength: 100 }), destinationStation: Type.String({ minLength: 1, maxLength: 100 }) }, { additionalProperties: false }), execute: (params, config, context) => invokeBridge("rail12306.timetable", params, config, context.signal) }),
  ],
});
