/**
 * Build the language server's initializationOptions.
 * `write` controls tangling on save. `pyrightCommand` replaces the
 * basedpyright argv. This module does not start a process.
 */

export interface LaunchSettings {
  readonly write: boolean;
  readonly pyrightCommand: readonly string[];
}

export interface InitializationOptions {
  readonly write: boolean;
  readonly pyrightCommand: readonly string[];
}

export function initializationOptions(
  settings: LaunchSettings,
): InitializationOptions {
  return {
    write: settings.write,
    pyrightCommand: [...settings.pyrightCommand],
  };
}
