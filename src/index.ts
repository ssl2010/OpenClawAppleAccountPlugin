import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

const plannedCapabilities = [
  "calendar.read",
  "calendar.create",
  "calendar.cancel",
  "reminders.read",
  "reminders.create",
  "reminders.complete",
  "notes.read.research",
] as const;

export default defineToolPlugin({
  id: "apple-account",
  name: "Apple Account",
  description: "Security-focused tools for personal Apple account data.",
  configSchema: Type.Object(
    {
      pythonPath: Type.Optional(Type.String()),
      sessionDirectory: Type.Optional(Type.String()),
      region: Type.Optional(Type.Union([Type.Literal("global"), Type.Literal("china")])),
    },
    { additionalProperties: false },
  ),
  tools: (tool) => [
    tool({
      name: "apple_account_capabilities",
      label: "Apple Account Capabilities",
      description: "Report the planned capability surface without accessing Apple account data.",
      parameters: Type.Object({}, { additionalProperties: false }),
      outputSchema: Type.Object(
        {
          status: Type.Literal("scaffold"),
          capabilities: Type.Array(Type.String()),
          notes: Type.String(),
        },
        { additionalProperties: false },
      ),
      execute: () => ({
        status: "scaffold" as const,
        capabilities: [...plannedCapabilities],
        notes: "No Apple credentials are read by this scaffold tool.",
      }),
    }),
  ],
});
