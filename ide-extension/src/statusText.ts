/**
 * Names and text for the hydra/status payload.
 * hydra/rebuild returns the same object. This module does not render UI.
 */

export const HYDRA_STATUS = "hydra/status";
export const HYDRA_REBUILD = "hydra/rebuild";

export interface StatusReport {
  readonly state: "busy" | "idle";
  readonly errors: number;
  readonly warnings: number;
}

export function statusLabel(report: StatusReport): string {
  if (report.state === "busy") {
    return "$(sync~spin) Hydra";
  }
  if (report.errors === 0 && report.warnings === 0) {
    return "Hydra";
  }
  return `Hydra: ${report.errors} errors, ${report.warnings} warnings`;
}

export function readStatus(value: unknown): StatusReport | undefined {
  const record = statusFields(value);
  if (record === undefined) {
    return undefined;
  }
  const state = record.state;
  if ((state !== "busy" && state !== "idle") || !isCount(record.errors)) {
    return undefined;
  }
  if (!isCount(record.warnings)) {
    return undefined;
  }
  return { state, errors: record.errors, warnings: record.warnings };
}

interface StatusFields {
  readonly state?: unknown;
  readonly errors?: unknown;
  readonly warnings?: unknown;
}

function statusFields(value: unknown): StatusFields | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return undefined;
  }
  return value as StatusFields;
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}
