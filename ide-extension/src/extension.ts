/**
 * Activate and deactivate the Hydra Tangler language client.
 * Wires one client for the first workspace folder. Does not tangle,
 * check, or translate diagnostics.
 */

import * as vscode from "vscode";

import { HydraClient } from "./client";

let client: HydraClient | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (folder === undefined) {
    return;
  }
  client = new HydraClient(folder);
  client.activate(context);
}

export async function deactivate(): Promise<void> {
  const current = client;
  client = undefined;
  if (current === undefined) {
    return;
  }
  await current.stop();
}
