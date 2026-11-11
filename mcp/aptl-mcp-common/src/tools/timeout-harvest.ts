import type { CommandTimeoutError } from '../ssh.js';
import { TIMEOUTS } from '../ssh-contracts.js';

/**
 * #1319: harvest a timed-out run_command's exec session once its stopped
 * command's channel has closed, so the broker's final records reach the run
 * directory. `harvest` is best-effort, as on the success path: a failure is
 * logged and the caller still returns the timeout error.
 *
 * Resolves once the harvest has finished, or after TIMEOUTS.REMOTE_CLOSE_AWAIT,
 * the bound close_session's remote-close wait uses (#304). A channel that stays
 * open longer is harvested in the background when it closes: OpenSSH holds a
 * forced-command session's close until the command exits.
 */
export async function harvestOnceClosed(
  timeout: CommandTimeoutError,
  harvest: (sessionId: string, runId: string | undefined) => Promise<boolean>,
): Promise<void> {
  const harvested = timeout.channelClosed.then(async () => {
    if (!(await harvest(timeout.sessionId, timeout.runId))) {
      console.error(`[captures] harvest after a run_command timeout failed for session ${timeout.sessionId}`);
    }
  });
  let timer: NodeJS.Timeout | undefined;
  const bound = new Promise<'open'>((resolve) => {
    timer = setTimeout(() => resolve('open'), TIMEOUTS.REMOTE_CLOSE_AWAIT);
  });
  if ((await Promise.race([harvested, bound])) === 'open') {
    console.error(
      `[captures] session ${timeout.sessionId} is still open after its run_command timeout; ` +
        'harvesting it when its channel closes',
    );
  }
  clearTimeout(timer);
}
