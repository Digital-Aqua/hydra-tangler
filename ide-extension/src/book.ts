/**
 * Locate the book a Hydra client should serve.
 * A book is the directory that contains `hydra.yaml`. The file is a
 * marker only; this module does not read it or talk to the editor.
 */

import * as path from "node:path";

export function bookDirectory(markerPath: string): string {
  return path.dirname(markerPath);
}
