/** Native completion evidence shared by the handlers and admission carrier. */
import { AsyncLocalStorage } from 'node:async_hooks';

const outcome = new AsyncLocalStorage<{ uncertain: boolean; signal?: AbortSignal }>();
const knownFailures = new WeakSet<object>();

/** Native owners mark validation failures or fully observed unsuccessful results.
 * Error text, status-like properties and caller payloads cannot establish this.
 */
export function knownToolFailure<T>(error: T): T {
  if (error !== null && typeof error === 'object') knownFailures.add(error);
  return error;
}

export function markToolFailure(error: unknown): void {
  if (error === null || typeof error !== 'object' || !knownFailures.has(error)) {
    markToolOutcomeUnknown();
  }
}

export function toolAbortSignal(): AbortSignal | undefined {
  return outcome.getStore()?.signal;
}

export function markToolOutcomeUnknown(): void {
  const active = outcome.getStore();
  if (active) active.uncertain = true;
}

export async function observeToolOutcome<T>(run: () => Promise<T>, signal?: AbortSignal) {
  const state = { uncertain: false, signal };
  const result = await outcome.run(state, run);
  return { result, uncertain: state.uncertain };
}
