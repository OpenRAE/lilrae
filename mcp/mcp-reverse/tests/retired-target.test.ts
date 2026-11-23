import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { getTargetCredentials, type LabConfig } from '../../aptl-mcp-common/src/config.js';

describe('retired default workstation', () => {
  it('does not grant SSH access to an undriven default target', () => {
    const config = JSON.parse(readFileSync(new URL('../docker-lab-config.json', import.meta.url), 'utf8')) as LabConfig;
    expect(() => getTargetCredentials(config)).toThrow('not enabled');
  });
});
