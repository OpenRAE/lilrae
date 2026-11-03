// Repository-owned OpenCode V1 plugin. No third-party imports or network destination.
import { readFileSync, openSync, writeSync, constants } from "node:fs";
import { createHash } from "node:crypto";

const digest = (value) => createHash("sha256").update(value).digest("hex");
const input = JSON.parse(readFileSync(new URL("./observer-input.json", import.meta.url), "utf8"));
const credentialName = "LILRAE_OPENCODE_PROVIDER_KEY";
const hashKeys = (value) => JSON.stringify(value && typeof value === "object"
  ? Array.isArray(value) ? value.map((v) => JSON.parse(hashKeys(v)))
    : Object.fromEntries(Object.keys(value).sort().map((k) => [k, JSON.parse(hashKeys(value[k]))]))
  : value);
const pick = (object, keys) => Object.fromEntries(keys.filter((k) => Object.hasOwn(object, k)).map((k) => [k, object[k]]));
const fail = () => { throw new Error("participant request observation refused"); };
const text = (content) => typeof content === "string" ? content
  : Array.isArray(content) ? content.filter((p) => p.type === "text" && typeof p.text === "string").map((p) => p.text).join("") : "";
const count = (value) => Number.isSafeInteger(value) && value >= 0 ? value : undefined;
const amount = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1000000 ? value : undefined;

export const RequestObserver = async () => ({
  config: async (config) => {
    const credential = process.env[credentialName];
    if (!credential || !input.endpoint || !/^[a-f0-9]{64}$/.test(input.observer_sha256)) fail();
    if (config.plugin?.length !== 1) fail();
    const nativeTurns = config.agent?.build?.steps ?? null;
    if (nativeTurns !== input.native_turn_limit) fail();
    let completedTurns = 0;
    const secrets = [credential];
    for (const server of Object.values(config.mcp ?? {})) {
      for (const [key, value] of Object.entries(server.environment ?? {})) {
        if (/AUTH|KEY|TOKEN|PASS|CREDENTIAL|SECRET/i.test(key) && typeof value === "string" && value) secrets.push(value);
      }
    }
    const label = (value, pattern = /^[A-Za-z0-9][A-Za-z0-9 ._/:@+-]*$/) =>
      typeof value === "string" && value.length <= 256 && pattern.test(value)
      && !secrets.some((secret) => value.includes(secret)) ? value : undefined;
    const fd = openSync(new URL("./provider-observations.jsonl", import.meta.url),
      constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    let written = 0;
    let calls = 0;
    const write = (event) => {
      const bytes = Buffer.from(JSON.stringify(event) + "\n");
      if (bytes.length > 131072 || written + bytes.length > 16 * 1024 * 1024) fail();
      if (writeSync(fd, bytes) !== bytes.length) fail();
      written += bytes.length;
    };
    write({ kind: "ready", observer_sha256: input.observer_sha256, native_turn_limit: nativeTurns });
    const observedFetch = async (url, init = {}) => {
      if (String(url) !== input.endpoint + "/chat/completions" || init.method !== "POST"
        || typeof init.body !== "string" || Buffer.byteLength(init.body) > 1024 * 1024 || calls >= 10000 || (nativeTurns !== null && completedTurns >= nativeTurns)) fail();
      const body = JSON.parse(init.body);
      const allowed = new Set(["model", "messages", "provider", "reasoning", "temperature", "top_p", "seed", "max_tokens", "stream", "stream_options", "usage", "tools", "tool_choice", "parallel_tool_calls"]);
      if (Object.keys(body).some((key) => !allowed.has(key))) fail();
      const controls = pick(body, ["model", "provider", "reasoning", "temperature", "top_p", "seed", "max_tokens", "stream"]);
      if (hashKeys(controls) !== hashKeys(input.controls)) fail();
      for (const key of ["stream_options", "usage"]) {
        if (Object.hasOwn(body, key)) {
          const value = body[key];
          if (!value || Object.keys(value).some((k) => !["include", "include_usage"].includes(k) || value[k] !== true)) fail();
          controls[key] = value;
        }
      }
      if (!Array.isArray(body.messages) || !body.messages.length || body.messages.length > 4096) fail();
      let matches = 0;
      const context = body.messages.map((message) => {
        if (!["system", "user", "assistant", "tool"].includes(message.role)) fail();
        const content = typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? null);
        const result = { role: message.role, content_sha256: digest(content) };
        if (message.role === "user") {
          const prefix = Buffer.from(text(message.content)).subarray(0, input.prompt_bytes);
          if (digest(prefix) === input.prompt_sha256) {
            result.authored_prefix_sha256 = digest(prefix);
            matches++;
          }
        }
        return result;
      });
      if (matches !== 1) fail();
      const call_id = ++calls;
      let ended = false;
      const end = (state) => {
        if (ended) return;
        write({ kind: "end", call_id, timestamp_ms: Date.now(), state });
        if (state === "completed") completedTurns++;
        ended = true;
      };
      write({ kind: "request", call_id, timestamp_ms: Date.now(), controls, context });
      const abort = () => end("cancelled");
      if (init.signal?.aborted) { abort(); fail(); }
      init.signal?.addEventListener("abort", abort, { once: true });
      let response;
      try { response = await fetch(url, { ...init, redirect: "error" }); }
      catch { end(init.signal?.aborted ? "cancelled" : "failed"); init.signal?.removeEventListener("abort", abort); fail(); }
      if (!response.ok || !response.body || !response.headers.get("content-type")?.includes("text/event-stream")) {
        write({ kind: "response", call_id, timestamp_ms: Date.now(), http_status: response.status, response: {} });
        end("failed");
        init.signal?.removeEventListener("abort", abort);
        return response;
      }
      const decoder = new TextDecoder();
      let buffer = "";
      let previous = "";
      let done = false;
      let metadata = {};
      const event = (record) => {
        if (ended) return;
        const data = record.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
        if (!data) return;
        if (data === "[DONE]") { done = true; return; }
        const value = JSON.parse(data);
        const usage = value.usage ?? {};
        const next = {
          generation_id: label(value.id, /^(gen-|chatcmpl-|resp_)[A-Za-z0-9_-]+$/),
          model: label(value.model), provider: label(value.provider),
          input_tokens: count(usage.prompt_tokens ?? usage.input_tokens),
          output_tokens: count(usage.completion_tokens ?? usage.output_tokens),
          reasoning_tokens: count(usage.completion_tokens_details?.reasoning_tokens ?? usage.reasoning_tokens),
          cache_read_tokens: count(usage.prompt_tokens_details?.cached_tokens ?? usage.cache_read_input_tokens),
          cache_write_tokens: count(usage.cache_creation_input_tokens), cost: amount(usage.cost),
          finish_reason: ["stop", "length", "tool_calls", "content_filter", "function_call"].includes(value.choices?.[0]?.finish_reason) ? value.choices[0].finish_reason : undefined,
        };
        for (const [key, item] of Object.entries(next)) {
          if (item === undefined) continue;
          if (key === "generation_id" && metadata[key] !== undefined && metadata[key] !== item) fail();
          metadata[key] = item;
        }
        const snapshot = JSON.stringify(metadata);
        if (snapshot !== previous) {
          write({ kind: "response", call_id, timestamp_ms: Date.now(), http_status: response.status, response: metadata });
          previous = snapshot;
        }
      };
      const stream = response.body.pipeThrough(new TransformStream({
        transform(chunk, controller) {
          buffer += decoder.decode(chunk, { stream: true });
          const records = buffer.split(/\r?\n\r?\n/);
          buffer = records.pop();
          if (Buffer.byteLength(buffer) > 131072 || records.some((r) => Buffer.byteLength(r) > 131072)) fail();
          for (const record of records) event(record);
          controller.enqueue(chunk);
        },
        flush() {
          buffer += decoder.decode();
          if (buffer.trim()) event(buffer);
          end(done && metadata.finish_reason ? "completed" : "failed");
          init.signal?.removeEventListener("abort", abort);
        },
      }));
      return new Response(stream, { status: response.status, statusText: response.statusText, headers: response.headers });
    };
    // Keep native provider access disabled until the journal and wrapper exist.
    Object.assign(config.provider.openrouter.options, { fetch: observedFetch, baseURL: input.endpoint, apiKey: credential });
  },
});
