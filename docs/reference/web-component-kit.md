# Web component kit reference

The source owners are `web/src/app.css` and `web/src/lib/components/kit/`.
`index.ts` exports the primitives and shared recipes.
The [design explanation](../specs/web-component-kit.md) states the reasons for this kit.

## Token groups

| Group | Tokens | Role |
| --- | --- | --- |
| Surface | `aptl-bg`, `aptl-surface`, `aptl-surface-hover`, `aptl-border` | Backgrounds, raised surfaces, and dividers |
| Text | `aptl-text`, `aptl-text-muted` | Primary and secondary text |
| Accent/status | `aptl-indigo`, `aptl-indigo-hover`, `aptl-violet`, `aptl-teal`, `aptl-red`, `aptl-green`, `aptl-amber` | Accent and semantic status colors |
| Focus | `aptl-focus` | Shared visible focus indicator |
| Typography | `font-sans`, `font-mono` | Interface and terminal/command fonts |

Tailwind v4 maps `--color-aptl-surface` to utilities such as `bg-aptl-surface` and `border-aptl-surface`.
`app.css` owns token values and color modes.
`tone.ts` owns class recipes rather than copies of those values.

## Primitives

| Component | Purpose | Key props |
| --- | --- | --- |
| `Badge` | Tags and labels | `tone`, `dot`, `pulse`, `label` |
| `StatusBadge` | Status with a dot and visible label | `tone`, `label`, `pulse` |
| `Button` | Action or link | `variant`, `size`, `href`, `disabled`, `label` |
| `Field` | Label, description, and error context | `label`, `description`, `error`, `required` |
| `TextInput` | Input using parent field context | `value`, `type`, `invalid`, `ariaLabel` |
| `Select` | Selection using parent field context | `value`, `options`, `invalid`, `ariaLabel` |
| `Table` | Captioned data with selectable density | `caption`, `captionVisible`, `density` |
| `Dialog` | Modal or side drawer | `open`, `title`, `description`, `placement` |
| `Menu` | Keyboard-accessible dropdown | `label`, `items`, `align` |

These are key props, not a replacement for the source interfaces.
`Tone` is `neutral`, `info`, `success`, `warning`, `danger`, or `accent`.
Button variants are `primary`, `secondary`, `ghost`, and `danger`.
Button sizes are `sm` and `md`.
Density is `comfortable` or `compact`.

## Field context

`Field` supplies control IDs, `aria-describedby`, invalid state, and required state through Svelte context.
Its error message uses `role="alert"`.
Controls outside a Field can use their own props and `ariaLabel`.

```svelte
<Field label="Row limit" description="The backend remains authoritative.">
  <TextInput />
</Field>
```

## Focus and motion

Dialog uses `role="dialog"`, `aria-modal`, title/description, focus trapping, Escape, backdrop closure, and focus return.
Its placement selects a modal or right-side drawer.
Menu reports expanded state and uses `role="menu"`.
Arrow keys, Home, and End select enabled items.
Escape closes the menu and returns focus.
An outside click closes it without forcing focus back to the trigger.

Reduced-motion preference sets animations and transitions to `0.01ms` with one animation iteration.
It also disables smooth scrolling.
The explicit reduced-motion setting and system media query use the same policy.
Density persistence belongs to the existing preferences owner, not the component kit.
