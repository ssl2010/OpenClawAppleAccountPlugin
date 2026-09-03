import { describe, expect, it } from "vitest";

import plugin from "./index.js";

describe("apple-account plugin metadata", () => {
  it("uses the stable plugin id", () => {
    expect(plugin.id).toBe("apple-account");
  });
});
