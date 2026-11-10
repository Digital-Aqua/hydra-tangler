/**
 * Register Hydra: Rebuild and Hydra: Restart Server.
 * Shows a message when a command fails. Does not launch the server.
 */

import * as vscode from "vscode";

export const REBUILD_COMMAND = "hydra.rebuild";
export const RESTART_COMMAND = "hydra.restart";

export interface HydraCommandHost {
  rebuild(): Promise<void>;
  restart(): Promise<void>;
}

export function registerHydraCommands(
  context: vscode.ExtensionContext,
  host: HydraCommandHost,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand(REBUILD_COMMAND, () => {
      void showFailure(host.rebuild());
    }),
    vscode.commands.registerCommand(RESTART_COMMAND, () => {
      void showFailure(host.restart());
    }),
  );
}

export async function showFailure(work: Promise<void>): Promise<void> {
  try {
    await work;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await vscode.window.showErrorMessage(`Hydra: ${message}`);
  }
}
