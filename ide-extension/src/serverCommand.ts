/**
 * Choose the process that runs `hydra serve`.
 * An empty command uses `uv run --project <folder> hydra serve`.
 * This module does not start a process or read VS Code settings.
 */

export interface LaunchCommand {
  readonly command: string;
  readonly args: readonly string[];
  readonly cwd: string;
}

export function serverCommand(
  workspaceFolder: string,
  configured: readonly string[],
): LaunchCommand {
  if (configured.length === 0) {
    return defaultLaunch(workspaceFolder);
  }
  return configuredLaunch(workspaceFolder, configured);
}

function defaultLaunch(workspaceFolder: string): LaunchCommand {
  return {
    command: "uv",
    args: ["run", "--project", workspaceFolder, "hydra", "serve"],
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
