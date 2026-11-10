/**
 * Tests for the process chosen to run `hydra serve`.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { serverCommand } from "./serverCommand";

describe("serverCommand", () => {
  it("uses uv against the workspace when no command is configured", () => {
    const launch = serverCommand("/work/book", []);
    assert.deepEqual(launch, {
      command: "uv",
      args: ["run", "--project", "/work/book", "hydra", "serve"],
      cwd: "/work/book",
    });
  });

  it("keeps a workspace path with spaces as one argument", () => {
    const launch = serverCommand("/work/my book", []);
    assert.deepEqual(launch.args, [
      "run",
      "--project",
      "/work/my book",
      "hydra",
      "serve",
    ]);
  });

  it("uses a configured command and the workspace as its cwd", () => {
    const launch = serverCommand("/work/book", ["hydra", "serve"]);
    assert.deepEqual(launch, {
      command: "hydra",
      args: ["serve"],
      cwd: "/work/book",
    });
  });

  it("rejects a command that does not name a program", () => {
    assert.throws(
      () => serverCommand("/work/book", [""]),
      /must start with a program name/,
    );
  });

  it("rejects an empty argument", () => {
    assert.throws(
      () => serverCommand("/work/book", ["hydra", ""]),
      /empty argument/,
    );
  });
});
