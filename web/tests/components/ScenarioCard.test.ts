import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ScenarioCard from '../../src/lib/components/ScenarioCard.svelte';
import type { ScenarioSummary } from '../../src/lib/types';

const SCENARIO: ScenarioSummary = {
	id: 'fixture-operational',
	name: 'Fixture Operational',
	description: 'Default public APTL startup scenario backed by RAES SDL.',
	mode: 'purple',
	difficulty: 'advanced',
	estimated_minutes: 60,
	tags: ['soc', 'full-stack'],
	required_containers: ['host-a', 'host-b'],
	validation: { valid: true, detail: null },
	pack: {
		id: 'fixture-range',
		version: '0.1.0',
		set_digest: `sha256:${'a'.repeat(64)}`,
		maturity: 'built'
	}
};

function summary(overrides: Partial<ScenarioSummary> = {}): ScenarioSummary {
	return { ...SCENARIO, ...overrides };
}

describe('ScenarioCard', () => {
	it('renders the name and description', () => {
		render(ScenarioCard, { props: { scenario: SCENARIO } });
		expect(screen.getByText('Fixture Operational')).toBeTruthy();
		expect(screen.getByText(/Default public APTL startup scenario/)).toBeTruthy();
		expect(screen.getByText('fixture-range 0.1.0 · built')).toBeTruthy();
	});

	it('links to the scenario workbench route', () => {
		render(ScenarioCard, { props: { scenario: SCENARIO } });
		const link = screen.getByRole('link');
		expect(link.getAttribute('href')).toBe('/scenarios/fixture-operational');
	});

	it('shows mode, difficulty, duration, container count, and tags', () => {
		render(ScenarioCard, { props: { scenario: SCENARIO } });
		expect(screen.getByText('purple')).toBeTruthy();
		expect(screen.getByText('advanced')).toBeTruthy();
		expect(screen.getByText('~60 min')).toBeTruthy();
		expect(screen.getByText('2 containers')).toBeTruthy();
		expect(screen.getByText('soc')).toBeTruthy();
	});

	it('marks an invalid scenario as unavailable', () => {
		render(ScenarioCard, {
			props: {
				scenario: summary({ validation: { valid: false, detail: 'nope' } })
			}
		});
		expect(screen.getByText('unavailable')).toBeTruthy();
	});

	it('renders with only the catalog-owned facts', () => {
		render(ScenarioCard, {
			props: {
				scenario: summary({
					name: 'Minimal',
					description: '',
					mode: null,
					difficulty: null,
					estimated_minutes: null,
					tags: [],
					required_containers: []
				})
			}
		});
		expect(screen.getByText('Minimal')).toBeTruthy();
	});
});
