/**
 * Build the language server's initializationOptions.
 * `write` controls tangling on save. `pyrightCommand` replaces the
 * basedpyright checker argv. `pyrightServerCommand` replaces the
 * basedpyright language-server argv. `ruffCommand` replaces the ruff
 * checker argv.
 * This module does not start a process.
 */

export interface LaunchSettings {
  readonly write: boolean;
  readonly pyrightCommand: readonly string[];
  readonly pyrightServerCommand: readonly string[];
  readonly ruffCommand: readonly string[];
}

export interface InitializationOptions {
  readonly write: boolean;
  readonly pyrightCommand: readonly string[];
  readonly pyrightServerCommand: readonly string[];
  readonly ruffCommand: readonly string[];
}

export function initializationOptions(
  settings: LaunchSettings,
): InitializationOptions {
  return {
    write: settings.write,
    pyrightCommand: [...settings.pyrightCommand],
    pyrightServerCommand: [...settings.pyrightServerCommand],
    ruffCommand: [...settings.ruffCommand],
  };
}
