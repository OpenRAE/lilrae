import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

const pluginURL = new URL("../../../src/aptl/workbench/provider_capture.mjs", import.meta.url);

test("requests and retries retain membership without changing transport bytes", async () => {
  const root = mkdtempSync(join(tmpdir(), "lilrae-capture-test-"));
  const path = join(root, "capture.jsonl");
  writeFileSync(path, "", { mode: 0o600 });
  const calls = [];
  const response = 'data: {"id":"gen-1","model":"served-model","provider":"served-provider","choices":[{"delta":{"content":"answer"}}]}\n\ndata: {"id":"gen-1","usage":{"prompt_tokens":12,"completion_tokens":3}}\n\ndata: [DONE]\n\n';
  globalThis.fetch = async (...args) => {
    calls.push(args);
    if (calls.length === 1) throw new Error("private-provider-error");
    return new Response(response, { headers: { "content-type": "text/event-stream" } });
  };
  const { default: plugin } = await import(pluginURL);
  const hooks = await plugin({}, { path, maxBytes: 65536, endpoint: "http://127.0.0.1:7000/api/v1", invocationId: "outer-red" });
  const options = await hooks.auth.loader();
  const input = "http://127.0.0.1:7000/api/v1/chat/completions";
  const init = { method: "POST", headers: { authorization: "Bearer private-key" }, body: JSON.stringify({ model: "requested-model", messages: [{ role: "user", content: "prompt" }], max_tokens: 20 }) };
  await assert.rejects(options.fetch(input, init), /private-provider-error/);
  const result = await options.fetch(input, init);
  assert.equal(await result.text(), response);
  assert.equal(calls.length, 2);
  assert.equal(calls[1][0], input);
  assert.equal(calls[1][1], init);
  const bytes = readFileSync(path, "utf8");
  assert.ok(!bytes.includes("private-key"));
  assert.ok(!bytes.includes("private-provider-error"));
  const records = bytes.trim().split("\n").map(JSON.parse);
  const requests = records.filter((row) => row.kind === "request");
  assert.equal(requests.length, 2);
  assert.notEqual(requests[0].request_id, requests[1].request_id);
  assert.equal(requests[0].body, init.body);
  assert.ok(records.some((row) => row.kind === "request-failed"));
  assert.ok(records.some((row) => row.kind === "response" && JSON.parse(row.json).usage?.prompt_tokens === 12));
  assert.ok(records.some((row) => row.kind === "request-finished"));
  assert.ok(records.every((row) => row.invocation_id === "outer-red"));
  await assert.rejects(options.fetch("https://unapproved.invalid/chat/completions", init));
  assert.equal(calls.length, 2);
});
