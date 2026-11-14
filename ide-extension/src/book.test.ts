/**
 * Tests for the directory chosen from a hydra.yaml marker.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { bookDirectory } from "./book";

describe("bookDirectory", () => {
  it("uses the directory that contains hydra.yaml", () => {
    assert.equal(
      bookDirectory("/work/auriga-core/hydra.yaml"),
      "/work/auriga-core",
    );
  });
});
