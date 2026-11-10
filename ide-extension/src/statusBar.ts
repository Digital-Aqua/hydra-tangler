/**
 * Status-bar item driven by hydra/status.
 * Clicking it runs Hydra: Rebuild. This module does not start the server.
 */

import * as vscode from "vscode";

import { REBUILD_COMMAND } from "./commands";
import { statusLabel, type StatusReport } from "./statusText";

const idle: StatusReport = { state: "idle", errors: 0, warnings: 0 };

export class HydraStatusBar {
  private readonly item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100,
    );
    this.item.command = REBUILD_COMMAND;
    this.item.tooltip = "Hydra: Rebuild";
    this.apply(idle);
    this.item.show();
  }

  apply(report: StatusReport): void {
    this.item.text = statusLabel(report);
  }

  markBusy(): void {
    this.apply({ state: "busy", errors: 0, warnings: 0 });
  }

  clear(): void {
    this.apply(idle);
  }

  dispose(): void {
    this.item.dispose();
  }
}
