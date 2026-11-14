/**
 * One language client for the first workspace folder.
 * Starts `hydra serve`, applies hydra/status, and restarts when the
 * launch settings change. The server owns tangle, checks, and navigation.
 * Document sync is full text because the server advertises that mode.
 */

import * as vscode from "vscode";
import {
  LanguageClient,
  type DocumentSelector,
  type LanguageClientOptions,
  type ServerOptions,
} from "vscode-languageclient/node";

import { registerHydraCommands, showFailure } from "./commands";
import { initializationOptions } from "./options";
import { serverCommand } from "./serverCommand";
import { readHydraSettings } from "./settings";
import { HydraStatusBar } from "./statusBar";
import {
  HYDRA_REBUILD,
  HYDRA_STATUS,
  readStatus,
  type StatusReport,
} from "./statusText";

const launchKeys = [
  "hydra.serverCommand",
  "hydra.write",
  "hydra.pyrightCommand",
  "hydra.pyrightServerCommand",
  "hydra.ruffCommand",
];

export class HydraClient {
  private language: LanguageClient | undefined;
  private chain: Promise<void> = Promise.resolve();
  private readonly status = new HydraStatusBar();
  private readonly output = vscode.window.createOutputChannel("Hydra Tangler", {
    log: true,
  });

  constructor(
    private readonly folder: vscode.WorkspaceFolder,
    private readonly project: string,
  ) {}

  activate(context: vscode.ExtensionContext): void {
    context.subscriptions.push(
      this.status,
      this.output,
      vscode.workspace.onDidChangeConfiguration((event) => {
        this.onConfiguration(event);
      }),
    );
    registerHydraCommands(context, {
      rebuild: () => this.rebuild(),
      restart: () => this.restart(),
    });
    void showFailure(this.restart());
  }

  stop(): Promise<void> {
    return this.enqueue(() => this.stopLanguage());
  }

  private onConfiguration(event: vscode.ConfigurationChangeEvent): void {
    if (!launchChanged(event, this.folder)) {
      return;
    }
    void showFailure(this.restart());
  }

  private restart(): Promise<void> {
    return this.enqueue(() => this.replace());
  }

  private async rebuild(): Promise<void> {
    const language = this.running();
    const payload: unknown = await language.sendRequest(HYDRA_REBUILD, {});
    const report = readStatus(payload);
    if (report === undefined) {
      throw new Error("rebuild returned an unexpected status");
    }
    this.status.apply(report);
  }

  private running(): LanguageClient {
    const language = this.language;
    if (language === undefined || !language.isRunning()) {
      throw new Error("language server is not running");
    }
    return language;
  }

  private enqueue(step: () => Promise<void>): Promise<void> {
    const run = this.chain.then(step);
    // A failed step must not stall later restarts. The caller still sees it.
    this.chain = run.then(settled, settled);
    return run;
  }

  private async replace(): Promise<void> {
    await this.stopLanguage();
    const language = this.createLanguage();
    this.language = language;
    this.status.markBusy();
    try {
      await language.start();
    } catch (error) {
      this.language = undefined;
      this.status.clear();
      await this.stopOne(language);
      throw error;
    }
  }

  private async stopLanguage(): Promise<void> {
    const language = this.language;
    this.language = undefined;
    if (language === undefined) {
      return;
    }
    await language.stop();
  }

  private async stopOne(language: LanguageClient): Promise<void> {
    try {
      await language.stop();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.output.appendLine(`Hydra stop failed: ${message}`);
    }
  }

  private createLanguage(): LanguageClient {
    const settings = readHydraSettings(this.folder);
    const launch = serverCommand(
      this.folder.uri.fsPath,
      settings.serverCommand,
      this.project,
    );
    const serverOptions: ServerOptions = {
      command: launch.command,
      args: [...launch.args],
      options: { cwd: launch.cwd },
    };
    const clientOptions: LanguageClientOptions = {
      documentSelector: markdownIn(this.folder),
      initializationOptions: initializationOptions(settings),
      workspaceFolder: this.folder,
      outputChannel: this.output,
    };
    const language = new LanguageClient(
      "hydra",
      "Hydra Tangler",
      serverOptions,
      clientOptions,
    );
    listenForStatus(language, (report) => {
      this.status.apply(report);
    });
    return language;
  }
}

function settled(): void {
  return undefined;
}

function listenForStatus(
  language: LanguageClient,
  onStatus: (report: StatusReport) => void,
): void {
  language.onNotification(HYDRA_STATUS, (params: unknown) => {
    const report = readStatus(params);
    if (report === undefined) {
      language.warn("Ignored a hydra/status notification with an unexpected shape.");
      return;
    }
    onStatus(report);
  });
}

function markdownIn(folder: vscode.WorkspaceFolder): DocumentSelector {
  const root = folder.uri.fsPath.replaceAll("\\", "/");
  return [
    {
      language: "markdown",
      scheme: "file",
      pattern: `${root}/**/*`,
    },
  ];
}

function launchChanged(
  event: vscode.ConfigurationChangeEvent,
  folder: vscode.WorkspaceFolder,
): boolean {
  for (const key of launchKeys) {
    if (event.affectsConfiguration(key, folder)) {
      return true;
    }
  }
  return false;
}
