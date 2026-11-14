/**
 * Choose the process that runs `hydra serve`.
 * An empty command uses `uv run --project <project> hydra serve`.
 * The project is the Hydra package; the working directory is the book.
 * This module does not start a process or read VS Code settings.
 */

import * as fs from "node:fs";
import * as path from "node:path";

export interface LaunchCommand {
  readonly command: string;
  readonly args: readonly string[];
  readonly cwd: string;
}

export function projectDirectory(
  extensionPath: string,
  workspaceFolder: string,
): string {
  const installed = fs.realpathSync(extensionPath);
  const beside = path.resolve(installed, "..");
  if (fs.existsSync(path.join(beside, "pyproject.toml"))) {
    return beside;
  }
  return workspaceFolder;
}

export function serverCommand(
  workspaceFolder: string,
  configured: readonly string[],
  project: string = workspaceFolder,
): LaunchCommand {
  if (configured.length === 0) {
    return defaultLaunch(workspaceFolder, project);
  }
  return configuredLaunch(workspaceFolder, configured);
}

function defaultLaunch(workspaceFolder: string, project: string): LaunchCommand {
  return {
    command: "uv",
    args: ["run", "--project", project, "hydra", "serve"],
    cwd: workspaceFolder,
  };
}

function configuredLaunch(
  workspaceFolder: string,
  configured: readonly string[],
): LaunchCommand {
  const [command, ...args] = configured;
  if (command === undefined || command.length === 0) {
    throw new Error("hydra.serverCommand must start with a program name");
  }
  for (const arg of args) {
    if (arg.length === 0) {
      throw new Error("hydra.serverCommand contains an empty argument");
    }
  }
  return { command, args, cwd: workspaceFolder };
}
