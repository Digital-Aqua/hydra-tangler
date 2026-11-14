/**
 * Activate and deactivate the Hydra Tangler language client.
 * Wires one client for the directory that contains hydra.yaml.
 * Does not tangle, check, or translate diagnostics.
 */

import * as path from "node:path";
import * as vscode from "vscode";

import { bookDirectory } from "./book";
import { HydraClient } from "./client";
import { projectDirectory } from "./serverCommand";

const marker = "**/hydra.yaml";
const skipped = "**/{node_modules,_build,.git,.venv}/**";

let client: HydraClient | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const book = await findBook();
  if (book === undefined) {
    return;
  }
  const project = projectDirectory(context.extensionPath, book.uri.fsPath);
  client = new HydraClient(book, project);
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

async function findBook(): Promise<vscode.WorkspaceFolder | undefined> {
  const matches = await vscode.workspace.findFiles(marker, skipped, 1);
  const found = matches[0];
  if (found === undefined) {
    return undefined;
  }
  const directory = bookDirectory(found.fsPath);
  const workspace = vscode.workspace.getWorkspaceFolder(found);
  return {
    uri: vscode.Uri.file(directory),
    name: path.basename(directory),
    index: workspace?.index ?? 0,
  };
}
