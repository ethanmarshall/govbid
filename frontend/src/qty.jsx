import { useEffect, useMemo, useState } from 'react'

// One build quantity instead of preset price breaks. Every quote prices 1 unit (the reference) and the quantity
// you are building, so changing 60 to 75 reprices at 75.

export const toBuild = (v) => Math.max(1, Math.floor(Number(v)) || 1)
export const buildList = (n) => (toBuild(n) > 1 ? [1, toBuild(n)] : [1])

// Saved quotes from before (with several breaks) reopen at the quantity that was quoted, else the largest one
export const buildFromSaved = (quantities, quoted) => toBuild(quoted || Math.max(...(quantities?.length ? quantities : [1])))

export function useBuildQty(initial = 1, setPick) {
  const [qtyText, setQtyText] = useState(String(initial))
  const build = toBuild(qtyText)
  const quantities = useMemo(() => buildList(build), [build])
  useEffect(() => { setPick?.(build) }, [build])
  return { qtyText, setQtyText, build, quantities }
}

export function BuildQtyInput({ value, onChange, label = 'Units to build', unit = 'units' }) {
  return (
    <label className="f">{label}
      <input type="number" min="1" step="1" inputMode="numeric" value={value}
        onChange={(e) => onChange(e.target.value)} onBlur={(e) => onChange(String(toBuild(e.target.value)))} aria-label={`${label} (${unit})`} />
    </label>
  )
}
