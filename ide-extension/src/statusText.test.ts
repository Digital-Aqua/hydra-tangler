/**
 * Tests for hydra/status text and payload parsing.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { readStatus, statusLabel } from "./statusText";

describe("statusLabel", () => {
  it("shows a spinner while the server is busy", () => {
    assert.equal(
      statusLabel({ state: "busy", errors: 2, warnings: 1 }),
      "$(sync~spin) Hydra",
    );
  });

  it("shows Hydra when the idle server has nothing to report", () => {
    assert.equal(statusLabel({ state: "idle", errors: 0, warnings: 0 }), "Hydra");
  });

  it("shows both counts when the idle server has diagnostics", () => {
    assert.equal(
      statusLabel({ state: "idle", errors: 1, warnings: 0 }),
      "Hydra: 1 errors, 0 warnings",
    );
  });
});

describe("readStatus", () => {
  it("reads a status payload", () => {
    assert.deepEqual(readStatus({ state: "idle", errors: 3, warnings: 4 }), {
      state: "idle",
      errors: 3,
      warnings: 4,
    });
  });

  it("rejects a payload that is not a status object", () => {
    assert.equal(readStatus(null), undefined);
    assert.equal(readStatus(["idle"]), undefined);
    assert.equal(readStatus({ state: "busy", errors: -1, warnings: 0 }), undefined);
    assert.equal(readStatus({ state: "other", errors: 0, warnings: 0 }), undefined);
    assert.equal(readStatus({ state: "idle", errors: 1.5, warnings: 0 }), undefined);
  });
});
