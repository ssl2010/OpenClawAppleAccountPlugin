import { describe, expect, it } from "vitest";
import { getToolPluginMetadata } from "openclaw/plugin-sdk/tool-plugin";

import plugin from "./index.js";

describe("apple-account plugin metadata", () => {
  it("uses the stable plugin id", () => {
    expect(plugin.id).toBe("apple-account");
  });

  it("registers read, write, and deterministic 12306 planning tools", () => {
    const metadata = getToolPluginMetadata(plugin);
    const names = metadata?.tools.map((tool) => tool.name) ?? [];
    expect(names).toContain("apple_account_status");
    expect(names).toContain("apple_calendar_create_event");
    expect(names).toContain("apple_calendar_delete_event");
    expect(names).toContain("apple_rail12306_plan_email");
    expect(names).toContain("rail12306_lookup_timetable");
    expect(metadata?.tools.find((item) => item.name === "apple_calendar_delete_event")?.optional).toBe(true);
  });
});
