# APTL web component kit

The kit gives the web workbench a small shared presentation and interaction layer.
It extends the existing Tailwind v4 tokens rather than adding a separate admin template.
Svelte routes compose the primitives instead of repeating their focus, color, and form behavior.
The historical UI-008b issue identifies this component-design work.

## Design tokens

`web/src/app.css` owns token values.
`web/src/lib/components/kit/tone.ts` maps semantic intent to Tailwind classes.
JavaScript does not keep another copy of the color values.
This gives palette changes one owner.

### Token groups

The [token Reference](../reference/web-component-kit.md#token-groups) lists the shared groups.
Status meaning uses text and context as well as color.
Purple remains an accent rather than the only status signal.

### Reduced motion

Global CSS honors system reduced-motion preferences and the explicit application setting.
It uses minimal animation and transition durations rather than depending on every component author to remember a guard.
The [motion Reference](../reference/web-component-kit.md#focus-and-motion) states the exact behavior.

### Density

Density belongs to presentation props such as Table's `density`.
The kit does not persist preferences.
The existing operator-preferences owner handles that separate concern.

## Primitives

`web/src/lib/components/kit/index.ts` exports the shared primitives.
Their semantic props keep visual decisions consistent across routes.
The [primitive Reference](../reference/web-component-kit.md#primitives) lists components and key props.
The source interfaces remain authoritative; the table does not declare another schema.

### Semantic tones

Badges and validation states share one `Tone` vocabulary.
The recipes map that vocabulary to the palette.
A route therefore does not need its own color switch for the same status.

### Forms

Field context keeps the control, label, description, and error relationship together.
It avoids manually passing a separate group of IDs through every caller.
The [field Reference](../reference/web-component-kit.md#field-context) contains the exact relationships and example.

### Overlays and accessibility

Dialog and Menu own their focus behavior without another component-library dependency.
This keeps the runtime small and makes the focus contract directly testable.
The [focus Reference](../reference/web-component-kit.md#focus-and-motion) describes keyboard behavior and closure.
The kit's accessibility behavior does not prove accessibility of every assembled route.

## Testing

Existing tests under `web/tests/components/kit/` exercise recipes, field wiring, focus trapping/return, and menu navigation.
They provide behavior evidence rather than a screenshot-only comparison.
Behavior tests run in CI or an approved isolated VM.
Their targeted paths qualify the changed component; the full web suite remains CI-only.
