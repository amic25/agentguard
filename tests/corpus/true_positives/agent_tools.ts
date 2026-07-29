// Node child-process execution reachable from agent output.
import { execSync } from "child_process";

export function runTool(command: string): void {
  execSync(command);
}
