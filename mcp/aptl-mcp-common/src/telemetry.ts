/**
 * OpenTelemetry tracing for APTL MCP servers.
 *
 * Replaces the former ToolTracer JSONL system with OTel spans exported
 * via OTLP HTTP/protobuf to the OTel Collector.
 *
 * Cross-process propagation: reads `.aptl/trace-context.json` written
 * by `aptl scenario start` so that MCP tool spans share the same
 * trace_id as scenario lifecycle spans from the Python CLI.
 */

import { readFileSync, existsSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

import { context, trace, Tracer, Context, SpanStatusCode, SpanKind } from '@opentelemetry/api';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { NodeTracerProvider, BatchSpanProcessor } from '@opentelemetry/sdk-trace-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';
import { ATTR_SERVICE_NAME } from '@opentelemetry/semantic-conventions';

import { redact } from './redaction.js';
import { RedactingSpanExporter } from './telemetry-export.js';

let provider: NodeTracerProvider | null = null;

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

/**
 * Configure OTel TracerProvider with OTLP HTTP exporter.
 * Safe to call multiple times — subsequent calls are no-ops.
 */
export function initTracing(serverName: string): void {
  if (provider !== null) return;

  const endpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';

  const resource = resourceFromAttributes({
    [ATTR_SERVICE_NAME]: serverName,
  });

  const exporter = new OTLPTraceExporter({
    url: `${endpoint}/v1/traces`,
  });

  provider = new NodeTracerProvider({
    resource,
    spanProcessors: [new BatchSpanProcessor(new RedactingSpanExporter(exporter))],
  });
  provider.register();

  console.error(`[OTel] Tracing initialized: service=${redact(serverName)} endpoint=${redact(endpoint)}`);
}

/**
 * Time allowed for the final flush and the provider shutdown together.
 *
 * The SIGTERM handler awaits shutdownTracing() before it closes SSH
 * sessions. Against an endpoint that does not answer, the OTLP exporter
 * retries for up to its 10 s export timeout, so an unbounded flush held
 * that teardown for 8-10 s whenever no collector was running. A reachable
 * collector accepts the last batch well inside this bound.
 */
const SHUTDOWN_EXPORT_BUDGET_MS = 500;

/**
 * Resolve true once `work` settles (fulfilled or rejected), or false if the
 * `deadline` (a performance.now() timestamp) passes first.
 */
async function settlesBefore(work: () => Promise<unknown>, deadline: number): Promise<boolean> {
  let timer: NodeJS.Timeout | undefined;
  const expired = new Promise<boolean>(resolve => {
    timer = setTimeout(resolve, Math.max(0, deadline - performance.now()), false);
  });
  // A rejection means the export failed or the Collector is unreachable:
  // tracing teardown must never crash the host process.
  const settled = Promise.resolve().then(work).then(() => true, () => true);
  try {
    return await Promise.race([settled, expired]);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Force-flush and shutdown the TracerProvider within
 * SHUTDOWN_EXPORT_BUDGET_MS.
 *
 * Flush/shutdown errors are swallowed. When the budget runs out, the
 * pending export is abandoned with a log line instead of delaying the
 * caller's own teardown.
 */
export async function shutdownTracing(): Promise<void> {
  if (provider === null) return;
  const closing = provider;
  provider = null;
  const deadline = performance.now() + SHUTDOWN_EXPORT_BUDGET_MS;
  const flushed = await settlesBefore(() => closing.forceFlush(), deadline);
  const closed = await settlesBefore(() => closing.shutdown(), deadline);
  if (!flushed || !closed) {
    console.error(
      `[OTel] Trace export did not finish within ${SHUTDOWN_EXPORT_BUDGET_MS} ms; pending spans may be lost`,
    );
  }
  console.error('[OTel] Tracing shut down');
}

/**
 * Return a Tracer from the current provider.
 */
export function getTracer(name: string = 'aptl-mcp'): Tracer {
  return trace.getTracer(name);
}

// ---------------------------------------------------------------------------
// Cross-process context
// ---------------------------------------------------------------------------

interface TraceContextFile {
  trace_id: string;
  span_id: string;
  trace_flags: string;
}

// Cache to avoid reading trace-context.json on every tool call
let cachedContext: Context | undefined;
let cachedMtimeMs: number = 0;
let cachedCtxPath: string = '';

/**
 * Read the trace context written by `aptl scenario start`.
 * Returns an OTel Context with the remote parent, or undefined if
 * no active scenario context exists.
 *
 * Results are cached by file mtime to avoid repeated disk reads
 * on every tool call.
 */
export function loadParentContext(): Context | undefined {
  const traceDir = process.env.APTL_STATE_DIR || '.aptl';
  const ctxPath = resolve(traceDir, 'trace-context.json');

  if (!existsSync(ctxPath)) {
    cachedContext = undefined;
    cachedMtimeMs = 0;
    return undefined;
  }

  // Check mtime — return cached result if file hasn't changed
  try {
    const mtimeMs = statSync(ctxPath).mtimeMs;
    if (ctxPath === cachedCtxPath && mtimeMs === cachedMtimeMs) {
      return cachedContext;
    }
    cachedCtxPath = ctxPath;
    cachedMtimeMs = mtimeMs;
  } catch {
    return cachedContext;
  }

  try {
    const raw = readFileSync(ctxPath, 'utf-8');
    const data: TraceContextFile = JSON.parse(raw);

    const spanContext = {
      traceId: data.trace_id,
      spanId: data.span_id,
      traceFlags: Number.parseInt(data.trace_flags, 16),
      isRemote: true,
    };

    // Validate hex lengths
    if (spanContext.traceId.length !== 32 || spanContext.spanId.length !== 16) {
      console.error('[OTel] Invalid trace context dimensions, ignoring');
      cachedContext = undefined;
      return undefined;
    }

    const parentSpan = trace.wrapSpanContext(spanContext);
    cachedContext = trace.setSpan(context.active(), parentSpan);
    return cachedContext;
  } catch (err) {
    console.error(`[OTel] Could not load trace context from ${ctxPath}: ${err}`);
    cachedContext = undefined;
    return undefined;
  }
}

// ---------------------------------------------------------------------------
// Tool call tracing (replaces ToolTracer.trace())
// ---------------------------------------------------------------------------

const MAX_ATTR_SIZE = 50_000;

/**
 * Truncate a value to a string suitable for a span attribute.
 */
function truncateAttr(value: unknown): string {
  const serialized = JSON.stringify(value);
  if (serialized && serialized.length > MAX_ATTR_SIZE) {
    return serialized.slice(0, 2000) + `... [truncated from ${serialized.length} bytes]`;
  }
  return serialized;
}

/**
 * Wrap a tool handler call with OTel span instrumentation.
 *
 * Creates a span with GenAI SIG conventions, records timing, errors,
 * and truncated arguments/responses as attributes.
 */
export async function traceToolCall<T>(
  toolName: string,
  serverName: string,
  args: Record<string, unknown>,
  handler: () => Promise<T>,
): Promise<T> {
  const tracer = getTracer();
  const parentContext = loadParentContext() || context.active();

  return tracer.startActiveSpan(
    'execute_tool',
    {
      kind: SpanKind.INTERNAL,
      attributes: {
        'gen_ai.operation.name': 'execute_tool',
        'gen_ai.tool.name': toolName,
        'gen_ai.agent.name': serverName,
        // Redact before truncating so the marker is never split mid-token.
        'aptl.tool.arguments': truncateAttr(redact(args)),
      },
    },
    parentContext,
    async (span) => {
      try {
        const result = await handler();
        span.setAttribute('aptl.tool.response', truncateAttr(redact(result)));
        span.setStatus({ code: SpanStatusCode.OK });
        return result;
      } catch (err) {
        const rawMessage = err instanceof Error ? err.message : String(err);
        // Error messages and stack traces from MCP tools regularly carry
        // the offending command line / response body / token verbatim.
        // Redact via the same boundary helper before they land in span
        // status, recordException event, or exported attributes.
        const safeMessage = String(redact(rawMessage));
        span.setStatus({ code: SpanStatusCode.ERROR, message: safeMessage });
        if (err instanceof Error) {
          // Build the OTel `exception` event manually rather than calling
          // `span.recordException(err)` so the auto-populated
          // `exception.message` / `exception.stacktrace` attributes go
          // through the same redactor.
          const safeStack = err.stack ? String(redact(err.stack)) : undefined;
          const eventAttrs: Record<string, string> = {
            'exception.type': err.name || 'Error',
            'exception.message': safeMessage,
          };
          if (safeStack !== undefined) {
            eventAttrs['exception.stacktrace'] = safeStack;
          }
          span.addEvent('exception', eventAttrs);
        }
        throw err;
      } finally {
        span.end();
      }
    },
  );
}

/**
 * Record a tool result's size and whether it was truncated on the active span.
 * Only counts are recorded, never the result content.
 */
export function recordToolResultSize(size: {
  originalChars: number;
  returnedChars: number;
  truncated: boolean;
}): void {
  trace.getActiveSpan()?.setAttributes({
    'aptl.tool.response_original_chars': size.originalChars,
    'aptl.tool.response_chars': size.returnedChars,
    'aptl.tool.response_truncated': size.truncated,
  });
}
