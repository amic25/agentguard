// ESM TypeScript module (.mts) - web content interpolated directly into a prompt.
import { callModel } from "./model.js";

export async function summarize(web_content: string): Promise<string> {
  const prompt = `Summarize the following page for the user: ${web_content}`;
  return callModel(prompt);
}
