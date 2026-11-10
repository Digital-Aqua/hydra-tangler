/**
 * Tests for initializationOptions sent to hydra serve.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { initializationOptions } from "./options";

describe("initializationOptions", () => {
  it("passes write and copies the pyright command", () => {
    const pyrightCommand = ["uv", "run", "basedpyright-langserver", "--stdio"];
    const options = initializationOptions({ write: true, pyrightCommand });
    assert.deepEqual(options, { write: true, pyrightCommand });
    pyrightCommand.push("extra");
    assert.equal(options.pyrightCommand.length, 4);
  });

  it("leaves write off and the pyright command empty by default", () => {
    const options = initializationOptions({ write: false, pyrightCommand: [] });
    assert.deepEqual(options, { write: false, pyrightCommand: [] });
  });
});
