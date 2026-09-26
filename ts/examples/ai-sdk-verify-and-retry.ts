/**
 * hardfacts in a Vercel AI SDK (v7) app: verify every draft, retry with feedback.
 *
 *   node examples/ai-sdk-verify-and-retry.ts
 *
 * Runs offline on the SDK's MockLanguageModelV4, scripted to invent a tracking number
 * on the first attempt. For production, swap in a real model, e.g.
 * `import { anthropic } from "@ai-sdk/anthropic"` and `anthropic("claude-sonnet-5")`.
 */

import { generateText, type ModelMessage } from "ai";
import { MockLanguageModelV4 } from "ai/test";

import { check, feedback } from "../src/index.ts";

const order = { order_id: "ORD-2024-0012", carrier: "Pos Laju", tracking: "EN123456789MY", eta: "2026-10-03" };

const reply = (text: string) => ({
  content: [{ type: "text" as const, text }],
  finishReason: { unified: "stop" as const, raw: undefined },
  usage: {
    inputTokens: { total: 120, noCache: 120, cacheRead: 0, cacheWrite: 0 },
    outputTokens: { total: 30, text: 30, reasoning: 0 },
  },
  warnings: [],
});

const model = new MockLanguageModelV4({
  doGenerate: [
    reply("Your parcel ORD-2024-0012 ships with Pos Laju. Tracking: EN123456780MY, arriving 2 October."),
    reply("Your parcel ORD-2024-0012 ships with Pos Laju. Tracking: EN123456789MY, arriving 3 October."),
  ],
});

async function answer(question: string, sources: unknown[], maxAttempts = 3): Promise<string> {
  const messages: ModelMessage[] = [{ role: "user", content: question }];
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const { text } = await generateText({
      model,
      system: `Answer only from this order record: ${JSON.stringify(sources)}`,
      messages,
    });
    const report = check(text, sources, { kinds: ["identifier", "date", "time", "money", "phone"] });
    console.log(`attempt ${attempt}: ${text}`);
    if (report.ok) return text;
    for (const c of report.unsupported) console.log(`  ✗ unsupported ${c.kind}: ${JSON.stringify(c.text)}`);
    messages.push({ role: "assistant", content: text }, { role: "user", content: feedback(report) });
  }
  return "I couldn't confirm those details; a colleague will follow up shortly."; // never send an unchecked draft
}

console.log("\nsent:", await answer("Where is my parcel?", [order]));
