/**
 * Tests for initializationOptions sent to hydra serve.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { initializationOptions } from "./options";

describe("initializationOptions", () => {
  it("passes write and copies the checker commands", () => {
    const pyrightCommand = ["uv", "run", "basedpyright", "--outputjson"];
    const pyrightServerCommand = [
      "uv",
      "run",
      "basedpyright-langserver",
      "--stdio",
    ];
    const ruffCommand = ["ruff", "check"];
    const options = initializationOptions({
      write: true,
      pyrightCommand,
      pyrightServerCommand,
      ruffCommand,
    });
    assert.deepEqual(options, {
      write: true,
      pyrightCommand,
      pyrightServerCommand,
      ruffCommand,
    });
    pyrightCommand.push("extra");
    pyrightServerCommand.push("--verbose");
    ruffCommand.push("--fix");
    assert.equal(options.pyrightCommand.length, 4);
    assert.equal(options.pyrightServerCommand.length, 4);
    assert.equal(options.ruffCommand.length, 2);
  });

  it("leaves write off and the commands empty by default", () => {
    const options = initializationOptions({
      write: false,
      pyrightCommand: [],
      pyrightServerCommand: [],
      ruffCommand: [],
    });
    assert.deepEqual(options, {
      write: false,
      pyrightCommand: [],
      pyrightServerCommand: [],
      ruffCommand: [],
    });
  });
});
