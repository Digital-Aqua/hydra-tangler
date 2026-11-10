/**
 * Read Hydra settings for one workspace folder.
 * Does not choose the server process or start it.
 */

import * as vscode from "vscode";

export interface HydraSettings {
  readonly serverCommand: readonly string[];
  readonly write: boolean;
  readonly pyrightCommand: readonly string[];
}

export function readHydraSettings(
  folder: vscode.WorkspaceFolder,
): HydraSettings {
  const config = vscode.workspace.getConfiguration("hydra", folder);
  return {
    serverCommand: readStrings(config.get("serverCommand"), "hydra.serverCommand"),
    write: config.get("write") === true,
    pyrightCommand: readStrings(
      config.get("pyrightCommand"),
      "hydra.pyrightCommand",
    ),
  };
}

function readStrings(value: unknown, name: string): readonly string[] {
  if (!Array.isArray(value)) {
    throw new Error(`${name} must be an array of strings`);
  }
  const words: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") {
      throw new Error(`${name} must be an array of strings`);
    }
    words.push(item);
  }
  return words;
}
