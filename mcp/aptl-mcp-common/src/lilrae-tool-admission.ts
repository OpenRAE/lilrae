/** One local carrier for RAES authority; no policy, retry, or history owner. */
import { randomUUID } from 'node:crypto';
import { createConnection, type Socket } from 'node:net';
import { isAbsolute } from 'node:path';
import { observeToolOutcome } from './lilrae-tool-outcome.js';

const MAX_FRAME = 1024 * 1024;
const REFUSAL = 'Participant tool call refused or outcome unknown.';
type ToolResult = { content: { type: string; text: string }[]; isError?: boolean };

export function participantToolRefusal(): ToolResult {
  return { isError: true, content: [{ type: 'text', text: JSON.stringify({ success: false, error: REFUSAL }) }] };
}

async function waitForNative<T>(run: () => Promise<T>, signal: AbortSignal): Promise<T> {
  signal.throwIfAborted();
  let stop: () => void = () => {};
  const interrupted = new Promise<never>((_, reject) => {
    stop = () => reject(new Error(REFUSAL));
    signal.addEventListener('abort', stop, { once: true });
  });
  try {
    return await Promise.race([
      Promise.resolve().then(() => { signal.throwIfAborted(); return run(); }),
      interrupted,
    ]);
  }
  finally { signal.removeEventListener('abort', stop); }
}

async function requestCleanup(cleanup: () => Promise<void>): Promise<void> {
  let timer: NodeJS.Timeout | undefined;
  try {
    await Promise.race([
      Promise.resolve().then(cleanup).catch(() => {}),
      new Promise<void>((resolve) => { timer = setTimeout(resolve, 1000); }),
    ]);
  } finally { clearTimeout(timer); }
}

class Channel {
  private buffered = Buffer.alloc(0);
  private readonly iterator: AsyncIterator<Buffer>;

  constructor(private readonly socket: Socket) {
    this.iterator = socket[Symbol.asyncIterator]();
  }

  write(value: unknown) {
    const data = Buffer.from(JSON.stringify(value) + '\n');
    if (data.length > MAX_FRAME) throw new Error(REFUSAL);
    this.socket.write(data);
  }

  async read(): Promise<Record<string, unknown>> {
    for (;;) {
      const newline = this.buffered.indexOf(10);
      if (newline >= 0) {
        const value = JSON.parse(this.buffered.subarray(0, newline).toString('utf8'));
        this.buffered = this.buffered.subarray(newline + 1);
        if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(REFUSAL);
        return value;
      }
      const next = await this.iterator.next();
      if (next.done || this.buffered.length + next.value.length > MAX_FRAME) throw new Error(REFUSAL);
      this.buffered = Buffer.concat([this.buffered, next.value]);
    }
  }
}

export class LilraeToolAdmission {
  constructor(private readonly path: string, private readonly token: string, private readonly timeout: number, private readonly configuration: unknown) {}

  async execute(tool: string, args: Record<string, unknown>, native: () => Promise<ToolResult>, cleanup: () => Promise<void>): Promise<ToolResult> {
    const socket = createConnection(this.path);
    const cancellation = new AbortController();
    const stop = () => cancellation.abort();
    const deadline = setTimeout(() => { stop(); socket.destroy(); }, this.timeout);
    socket.on('error', stop);
    socket.on('close', stop);
    const channel = new Channel(socket);
    let started = false;
    try {
      // A detached value is used for both the request and native invocation by
      // the common server. No caller-supplied participant coordinates cross IPC.
      channel.write({ version: 1, token: this.token, call_id: randomUUID(), tool, arguments: args, configuration: this.configuration });
      if ((await channel.read()).accepted !== true) throw new Error(REFUSAL);
      cancellation.signal.throwIfAborted();
      started = true;
      const observed = await waitForNative(() => observeToolOutcome(native, cancellation.signal), cancellation.signal);
      channel.write({ result: observed.uncertain ? null : observed.result, uncertain: observed.uncertain });
      const receipt = await channel.read();
      if (receipt.accepted !== true || !receipt.result || typeof receipt.result !== 'object') throw new Error(REFUSAL);
      const result = receipt.result as ToolResult;
      if (!Array.isArray(result.content) || result.content.some((item) => item.type !== 'text' || typeof item.text !== 'string')) throw new Error(REFUSAL);
      return result;
    } catch {
      stop();
      if (started) await requestCleanup(cleanup);
      // Disconnect tells the owner to retain uncertainty after dispatch. A
      // fixed failure never leaks the peer, token, arguments or handler error.
      return participantToolRefusal();
    } finally {
      clearTimeout(deadline);
      socket.off('close', stop);
      socket.destroy();
    }
  }
}

export function participantToolAdmission(configuration: unknown, environment: NodeJS.ProcessEnv = process.env): LilraeToolAdmission | undefined {
  const path = environment.LILRAE_TOOL_SOCKET;
  const token = environment.LILRAE_TOOL_TOKEN;
  const deadline = environment.LILRAE_TOOL_TIMEOUT_MS;
  if (path === undefined && token === undefined && deadline === undefined) return undefined;
  if (!path || !isAbsolute(path) || Buffer.byteLength(path) > 103 || !token || !/^[a-f0-9]{64}$/.test(token)
    || !deadline || !/^[1-9]\d*$/.test(deadline) || Number(deadline) > 3_600_000) {
    throw new Error('Participant tool transport configuration is invalid.');
  }
  return new LilraeToolAdmission(path, token, Number(deadline), structuredClone(configuration));
}
