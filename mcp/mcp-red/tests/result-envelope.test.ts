import { describe, it, expect } from 'vitest';
import { boundToolResult, type PostToolHookInfo } from 'aptl-mcp-common';
import { parseResultEnvelope, resultSessionId } from '../src/result-envelope.js';
import { deriveCommandOutcome } from '../src/logger.js';
import { isEffectiveRawCall } from '../src/effective-mode.js';

// The shape the postToolHook receives: the handler's pretty-printed envelope
// inside one text block.
function wrapped(envelope: unknown) {
  return { content: [{ type: 'text', text: JSON.stringify(envelope, null, 2) }] };
}

// Over the default budget of 4000 tokens (16000 characters).
const LONG_OUTPUT = Array.from({ length: 1000 }, (_, index) => `entry ${index} ${'v'.repeat(30)}`).join('\n');

function runCommandResult(stdout: string, code: number) {
  return wrapped({
    target: 'kali',
    command: 'ls -la /srv/data',
    username: 'kali',
    success: code === 0,
    output: { stdout, stderr: '', code, signal: null, sessionId: 'exec-42', mode: 'normal' },
  });
}

function sessionCommandResult(output: string, sessionMode: 'raw' | 'normal') {
  return wrapped({
    success: true,
    session_id: 's1',
    command: 'cat notes.txt',
    output,
    stderr: '',
    exit_code: 0,
    session_mode: sessionMode,
  });
}

function hookInfo(toolName: string, result: unknown): PostToolHookInfo {
  return { toolName, args: { command: 'x' }, result, durationMs: 1 };
}

describe('parseResultEnvelope', () => {
  it('parses the envelope inside the first text block', () => {
    expect(parseResultEnvelope(runCommandResult('ok', 0))).toMatchObject({ success: true });
  });

  it.each([
    ['no result', undefined],
    ['no text block', { content: [] }],
    ['text that is not JSON', { content: [{ type: 'text', text: 'plain' }] }],
    ['a JSON scalar', { content: [{ type: 'text', text: '7' }] }],
  ])('returns null for %s', (_label, result) => {
    expect(parseResultEnvelope(result)).toBeNull();
  });
});

describe('resultSessionId', () => {
  it('reads the exec session id from the run_command envelope text', () => {
    expect(resultSessionId(runCommandResult('ok', 0))).toBe('exec-42');
  });

  it.each([
    ['an envelope without output', wrapped({ success: false, error: 'boom' })],
    ['an output without a session id', wrapped({ output: { stdout: 'ok' } })],
    ['an empty session id', wrapped({ output: { sessionId: '' } })],
    ['a result object that is not MCP-shaped', { output: { sessionId: 'exec-42' } }],
  ])('returns undefined for %s', (_label, result) => {
    expect(resultSessionId(result)).toBeUndefined();
  });
});

// ADR-027: the hook takes the outcome and the effective mode from the result
// envelope. The common size limit must leave those fields readable.
describe('hook fields after the common size limit cuts a long output', () => {
  it('keeps the run_command exit code and session id', () => {
    const bounded = boundToolResult(runCommandResult(LONG_OUTPUT, 2), 4000);

    expect(bounded.truncated).toBe(true);
    expect(deriveCommandOutcome(bounded.result, undefined)).toEqual({ success: false, exit_code: 2 });
    expect(resultSessionId(bounded.result)).toBe('exec-42');
  });

  it.each([
    ['raw', true],
    ['normal', false],
  ] as const)('keeps the session_command exit code and session_mode=%s', (mode, raw) => {
    const bounded = boundToolResult(sessionCommandResult(LONG_OUTPUT, mode), 4000);
    const info = hookInfo('kali_session_command', bounded.result);

    expect(bounded.truncated).toBe(true);
    expect(deriveCommandOutcome(bounded.result, undefined)).toEqual({ success: true, exit_code: 0 });
    expect(isEffectiveRawCall(info)).toBe(raw);
  });
});
