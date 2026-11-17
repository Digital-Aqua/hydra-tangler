/**
 * Tests for the tangler=yaml fence injection grammar.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";

const grammar = JSON.parse(
  readFileSync(
    join(__dirname, "../syntaxes/tangler-yaml.tmLanguage.json"),
    "utf8",
  ),
) as { patterns: { begin: string }[] };

const begin = new RegExp(grammar.patterns[0].begin.replace("(^|\\G)", "^"));

describe("tangler yaml fence", () => {
  it("matches an openapi fence with tangler=yaml", () => {
    assert.match("```openapi file=a.yaml tangler=yaml", begin);
  });

  it('matches tangler="yml"', () => {
    assert.match('```openapi file=a.yaml tangler="yml"', begin);
  });

  it("matches tangler='yaml'", () => {
    assert.match("```openapi file=a.yaml tangler='yaml'", begin);
  });

  it("does not match a yaml fence with no tangler attribute", () => {
    assert.doesNotMatch("```yaml file=a.yaml", begin);
  });

  it("does not match tangler=python", () => {
    assert.doesNotMatch("```openapi file=a.yaml tangler=python", begin);
  });

  it("does not match tangler=yamlfoo", () => {
    assert.doesNotMatch("```openapi file=a.yaml tangler=yamlfoo", begin);
  });
});
