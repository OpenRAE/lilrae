// Repository-owned OpenCode V1 plugin. No third-party imports or network destination.
import { readFileSync, openSync, writeSync, constants } from "node:fs";
import { createHash } from "node:crypto";

const input = JSON.parse(readFileSync(new URL("./observer-input.json", import.meta.url), "utf8"));
const credentialName = "LILRAE_OPENCODE_PROVIDER_KEY";
const controlFields = ["model", "provider", "reasoning", "temperature", "top_p", "seed", "max_tokens", "stream"];
const requestFields = new Set([...controlFields, "messages", "stream_options", "usage", "tools", "tool_choice", "parallel_tool_calls"]);
const finishReasons = ["stop", "length", "tool_calls", "content_filter", "function_call"];
const digest = (value) => createHash("sha256").update(value).digest("hex");
const pick = (object, keys) => Object.fromEntries(keys.filter((key) => Object.hasOwn(object, key)).map((key) => [key, object[key]]));
const fail = () => { throw new Error("participant request observation refused"); };
const count = (value) => Number.isSafeInteger(value) && value >= 0 ? value : undefined;
const amount = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1000000 ? value : undefined;

function orderedValue(value) {
  if (Array.isArray(value)) return value.map(orderedValue);
  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort((left, right) => left.localeCompare(right, "en"));
    return Object.fromEntries(keys.map((key) => [key, orderedValue(value[key])]));
  }
  return value;
}

function messageText(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.filter((part) => part.type === "text" && typeof part.text === "string").map((part) => part.text).join("");
  return "";
}

function observerSecrets(config, credential) {
  const secrets = [credential];
  for (const server of Object.values(config.mcp ?? {})) {
    for (const [key, value] of Object.entries(server.environment ?? {})) {
      if (/AUTH|KEY|TOKEN|PASS|CREDENTIAL|SECRET/i.test(key) && typeof value === "string" && value) secrets.push(value);
    }
  }
  return secrets;
}

function safeLabel(secrets, value, pattern = /^[A-Za-z0-9][A-Za-z0-9 ._/:@+-]*$/) {
  return typeof value === "string" && value.length <= 256 && pattern.test(value)
    && !secrets.some((secret) => value.includes(secret)) ? value : undefined;
}

function journalWriter() {
  const fd = openSync(new URL("./provider-observations.jsonl", import.meta.url),
    constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  let written = 0;
  return (event) => {
    const bytes = Buffer.from(JSON.stringify(event) + "\n");
    if (bytes.length > 131072 || written + bytes.length > 16 * 1024 * 1024) fail();
    if (writeSync(fd, bytes) !== bytes.length) fail();
    written += bytes.length;
  };
}

function requestControls(body) {
  if (Object.keys(body).some((key) => !requestFields.has(key))) fail();
  const controls = pick(body, controlFields);
  if (JSON.stringify(orderedValue(controls)) !== JSON.stringify(orderedValue(input.controls))) fail();
  for (const key of ["stream_options", "usage"]) {
    if (Object.hasOwn(body, key)) {
      const value = body[key];
      if (!value || Object.keys(value).some((name) => !["include", "include_usage"].includes(name) || value[name] !== true)) fail();
      controls[key] = value;
    }
  }
  return controls;
}

function requestContext(messages) {
  if (!Array.isArray(messages) || !messages.length || messages.length > 4096) fail();
  let matches = 0;
  const context = messages.map((message) => {
    if (!["system", "user", "assistant", "tool"].includes(message.role)) fail();
    const content = typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? null);
    const result = { role: message.role, content_sha256: digest(content) };
    if (message.role === "user") {
      const prefix = Buffer.from(messageText(message.content)).subarray(0, input.prompt_bytes);
      if (digest(prefix) === input.prompt_sha256) {
        result.authored_prefix_sha256 = digest(prefix);
        matches++;
      }
    }
    return result;
  });
  if (matches !== 1) fail();
  return context;
}

function responseMetadata(value, secrets) {
  const usage = value.usage ?? {};
  return {
    generation_id: safeLabel(secrets, value.id, /^(gen-|chatcmpl-|resp_)[A-Za-z0-9_-]+$/),
    model: safeLabel(secrets, value.model), provider: safeLabel(secrets, value.provider),
    input_tokens: count(usage.prompt_tokens ?? usage.input_tokens),
    output_tokens: count(usage.completion_tokens ?? usage.output_tokens),
    reasoning_tokens: count(usage.completion_tokens_details?.reasoning_tokens ?? usage.reasoning_tokens),
    cache_read_tokens: count(usage.prompt_tokens_details?.cached_tokens ?? usage.cache_read_input_tokens),
    cache_write_tokens: count(usage.cache_creation_input_tokens), cost: amount(usage.cost),
    finish_reason: finishReasons.includes(value.choices?.[0]?.finish_reason) ? value.choices[0].finish_reason : undefined,
  };
}

function observedResponse(response, observation) {
  const { call, end, write, signal, abort, secrets } = observation;
  const decoder = new TextDecoder();
  let buffer = "";
  let previous = "";
  let done = false;
  const metadata = {};
  const event = (record) => {
    if (call.ended) return;
    const data = record.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
    if (!data) return;
    if (data === "[DONE]") { done = true; return; }
    const next = responseMetadata(JSON.parse(data), secrets);
    for (const [key, item] of Object.entries(next)) {
      if (item === undefined) continue;
      if (key === "generation_id" && metadata[key] !== undefined && metadata[key] !== item) fail();
      metadata[key] = item;
    }
    const snapshot = JSON.stringify(metadata);
    if (snapshot !== previous) {
      write({ kind: "response", call_id: call.id, timestamp_ms: Date.now(), http_status: response.status, response: metadata });
      previous = snapshot;
    }
  };
  const stream = response.body.pipeThrough(new TransformStream({
    transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });
      const records = buffer.split(/\r?\n\r?\n/);
      buffer = records.pop();
      if (Buffer.byteLength(buffer) > 131072 || records.some((record) => Buffer.byteLength(record) > 131072)) fail();
      for (const record of records) event(record);
      controller.enqueue(chunk);
    },
    flush() {
      buffer += decoder.decode();
      if (buffer.trim()) event(buffer);
      end(done && metadata.finish_reason ? "completed" : "failed");
      signal?.removeEventListener("abort", abort);
    },
  }));
  return new Response(stream, { status: response.status, statusText: response.statusText, headers: response.headers });
}

function createObservedFetch(write, nativeTurns, secrets) {
  const counters = { calls: 0, completedTurns: 0 };
  return async (url, init = {}) => {
    if (String(url) !== input.endpoint + "/chat/completions" || init.method !== "POST"
      || typeof init.body !== "string" || Buffer.byteLength(init.body) > 1024 * 1024 || counters.calls >= 10000
      || (nativeTurns !== null && counters.completedTurns >= nativeTurns)) fail();
    const body = JSON.parse(init.body);
    const controls = requestControls(body);
    const context = requestContext(body.messages);
    const call = { id: ++counters.calls, ended: false };
    const end = (state) => {
      if (call.ended) return;
      write({ kind: "end", call_id: call.id, timestamp_ms: Date.now(), state });
      if (state === "completed") counters.completedTurns++;
      call.ended = true;
    };
    write({ kind: "request", call_id: call.id, timestamp_ms: Date.now(), controls, context });
    const abort = () => end("cancelled");
    if (init.signal?.aborted) { abort(); fail(); }
    init.signal?.addEventListener("abort", abort, { once: true });
    let response;
    try { response = await fetch(url, { ...init, redirect: "error" }); }
    catch {
      end(init.signal?.aborted ? "cancelled" : "failed");
      init.signal?.removeEventListener("abort", abort);
      fail();
    }
    if (!response.ok || !response.body || !response.headers.get("content-type")?.includes("text/event-stream")) {
      write({ kind: "response", call_id: call.id, timestamp_ms: Date.now(), http_status: response.status, response: {} });
      end("failed");
      init.signal?.removeEventListener("abort", abort);
      return response;
    }
    return observedResponse(response, { call, end, write, signal: init.signal, abort, secrets });
  };
}

async function configureObserver(config) {
  const credential = process.env[credentialName];
  if (!credential || !input.endpoint || !/^[a-f0-9]{64}$/.test(input.observer_sha256)) fail();
  if (config.plugin?.length !== 1) fail();
  const nativeTurns = config.agent?.build?.steps ?? null;
  if (nativeTurns !== input.native_turn_limit) fail();
  const secrets = observerSecrets(config, credential);
  const write = journalWriter();
  write({ kind: "ready", observer_sha256: input.observer_sha256, native_turn_limit: nativeTurns });
  const observedFetch = createObservedFetch(write, nativeTurns, secrets);
  // Keep provider access disabled until the private journal and wrapper exist.
  Object.assign(config.provider.openrouter.options, { fetch: observedFetch, baseURL: input.endpoint, apiKey: credential });
}

export const RequestObserver = async () => ({ config: configureObserver });
