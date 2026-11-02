/**
 * Read the JSON envelope inside an MCP tool result.
 *
 * The postToolHook receives the result as the client receives it:
 * `{ content: [{ type: 'text', text: '<json envelope>' }] }`. Fields such as
 * `output.sessionId` are inside that text, not on the result object. The
 * common size limit keeps the envelope valid JSON, so these fields stay
 * readable after a long output is cut.
 */

/** Parse the first text block of a tool result as a JSON object, or null. */
export function parseResultEnvelope(toolResult: unknown): Record<string, unknown> | null {
  const content = (toolResult as { content?: { text?: string }[] } | undefined)?.content;
  const text = content?.[0]?.text;
  if (typeof text !== 'string') return null;
  try {
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed === 'object' && parsed !== null) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * The exec session id that one-shot `run_command` reports in
 * `output.sessionId` (OBS-003), or undefined when the envelope has none.
 */
export function resultSessionId(toolResult: unknown): string | undefined {
  const output = parseResultEnvelope(toolResult)?.output;
  if (typeof output !== 'object' || output === null) return undefined;
  const sessionId = (output as { sessionId?: unknown }).sessionId;
  return typeof sessionId === 'string' && sessionId.length > 0 ? sessionId : undefined;
}
