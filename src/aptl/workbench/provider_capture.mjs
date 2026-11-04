// Host-owned observer for the pinned OpenCode 1.19.5 provider fetch hook.
// No headers, credentials, extra requests, listeners, or external dependencies.
import { constants, openSync, fstatSync, writeSync, closeSync } from "node:fs";
import { randomUUID } from "node:crypto";

function observeResponse(response, requestId, append, maxBytes) {
  if (!response.body) {
    append("request-finished", requestId, { status: response.status, empty_body: true });
    return response;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const sse = (response.headers.get("content-type") || "").includes("text/event-stream");
  let buffered = "";
  let done = false;
  function accept(line) {
    const text = line.trim();
    if (!text || text.startsWith(":")) return;
    if (sse && !text.startsWith("data:")) {
      if (/^(event|id|retry):/.test(text)) return;
      throw new Error("capture stream refused");
    }
    const data = sse ? text.slice(5).trim() : text;
    if (data === "[DONE]") return;
    JSON.parse(data);
    append("response", requestId, { json: data });
  }
  function take(bytes, terminal = false) {
    buffered += decoder.decode(bytes, { stream: !terminal });
    if (Buffer.byteLength(buffered) > maxBytes) throw new Error("capture limit exceeded");
    if (sse) {
      let index;
      while ((index = buffered.indexOf("\n")) >= 0) {
        accept(buffered.slice(0, index));
        buffered = buffered.slice(index + 1);
      }
    }
    if (terminal && buffered.trim()) accept(buffered);
  }
  const stream = new ReadableStream({
    async pull(controller) {
      try {
        const part = await reader.read();
        if (part.done) {
          take(undefined, true);
          append("request-finished", requestId, { status: response.status });
          done = true;
          controller.close();
          return;
        }
        take(part.value);
        controller.enqueue(part.value);
      } catch (error) {
        try { append("response-failed", requestId); } catch { /* The missing terminal frame discloses this gap. */ }
        await reader.cancel().catch(() => {});
        controller.error(error);
      }
    },
    async cancel() {
      if (!done) append("response-cancelled", requestId);
      await reader.cancel();
    },
  });
  return new Response(stream, { status: response.status, statusText: response.statusText, headers: response.headers });
}

export default async function capturePlugin(_input, options) {
  const { path, maxBytes, endpoint, invocationId } = options;
  if (typeof path !== "string" || !Number.isSafeInteger(maxBytes) || maxBytes < 1024 ||
      maxBytes > 64 * 1024 * 1024 || !/^[A-Za-z0-9._:-]{1,128}$/.test(invocationId)) {
    throw new Error("capture configuration refused");
  }
  const allowed = new Set([`${endpoint}/chat/completions`, `${endpoint}/responses`]);
  const nativeFetch = globalThis.fetch;
  let sequence = 0;

  function append(kind, requestId, fields = {}) {
    const descriptor = openSync(path, constants.O_WRONLY | constants.O_APPEND | constants.O_NOFOLLOW);
    try {
      const stat = fstatSync(descriptor);
      if (!stat.isFile() || (stat.mode & 0o777) !== 0o600) throw new Error("capture file refused");
      const record = Buffer.from(JSON.stringify({
        kind, invocation_id: invocationId, request_id: requestId,
        sequence: sequence++, observed_at: new Date().toISOString(),
        monotonic_ms: performance.now(), ...fields,
      }) + "\n");
      if (record.length > maxBytes - stat.size) throw new Error("capture limit exceeded");
      let offset = 0;
      while (offset < record.length) offset += writeSync(descriptor, record, offset);
    } finally {
      closeSync(descriptor);
    }
  }


  append("capture-ready", null, { plugin_version: "1" });
  return {
    auth: {
      provider: "openrouter",
      methods: [],
      async loader() {
        return {
          async fetch(input, init) {
            const url = input instanceof Request ? input.url : String(input);
            if (!allowed.has(url) || typeof init?.body !== "string" || init.method !== "POST") {
              throw new Error("capture provider request refused");
            }
            // Strictly before dispatch: unavailable capture cannot start a request.
            const requestId = randomUUID();
            JSON.parse(init.body);
            append("request", requestId, { body: init.body });
            let response;
            try {
              response = await nativeFetch(input, init);
            } catch (error) {
              append("request-failed", requestId);
              throw error;
            }
            return observeResponse(response, requestId, append, maxBytes);
          },
        };
      },
    },
  };
}
