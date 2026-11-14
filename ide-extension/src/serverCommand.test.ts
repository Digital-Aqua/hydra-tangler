/**
 * Tests for the process chosen to run `hydra serve`.
 */

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, it } from "node:test";

import { projectDirectory, serverCommand } from "./serverCommand";

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

  it("runs hydra from a project beside the extension", () => {
    const launch = serverCommand("/work/book", [], "/opt/hydra-tangler");
    assert.deepEqual(launch, {
      command: "uv",
      args: ["run", "--project", "/opt/hydra-tangler", "hydra", "serve"],
      cwd: "/work/book",
    });
  });

  it("uses the package next to a development extension", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "hydra-"));
    const extension = path.join(root, "ide-extension");
    fs.mkdirSync(extension);
    fs.writeFileSync(path.join(root, "pyproject.toml"), "");
    assert.equal(projectDirectory(extension, "/work/book"), root);
  });

  it("follows a symlink to the development package", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "hydra-"));
    const extension = path.join(root, "ide-extension");
    const linkDir = fs.mkdtempSync(path.join(os.tmpdir(), "hydra-link-"));
    const link = path.join(linkDir, "digital-aqua.hydra-tangler-0.1.0");
    fs.mkdirSync(extension);
    fs.writeFileSync(path.join(root, "pyproject.toml"), "");
    fs.symlinkSync(extension, link);
    assert.equal(projectDirectory(link, "/work/book"), root);
  });

  it("uses the workspace when the extension is packaged", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "hydra-"));
    const extension = path.join(root, "hydra-tangler");
    fs.mkdirSync(extension);
    assert.equal(projectDirectory(extension, "/work/book"), "/work/book");
  });

  it("rejects an empty argument", () => {
    assert.throws(
      () => serverCommand("/work/book", ["hydra", ""]),
      /empty argument/,
    );
  });
});
