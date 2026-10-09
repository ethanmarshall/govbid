// Small markdown renderer for section previews. Matches what the Word export supports:
// headings, bullets, numbered lists, pipe tables, **bold**, *italic*, `code`.

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

function inline(s) {
  return esc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]/g, (m, inner) => (/^insert|^tbd|^add/i.test(inner) ? `<mark>[${inner}]</mark>` : m))
}

export function renderMarkdown(md) {
  const lines = (md || '').replace(/\r\n/g, '\n').split('\n')
  const out = []
  let i = 0
  let para = []
  const flush = () => {
    if (para.length) out.push(`<p>${inline(para.join(' '))}</p>`)
    para = []
  }
  while (i < lines.length) {
    const raw = lines[i]
    const line = raw.trim()
    if (!line) { flush(); i++; continue }
    let m = line.match(/^(#{1,4})\s+(.*)/)
    if (m) { flush(); const lvl = Math.min(3 + m[1].length - 1, 6); out.push(`<h${lvl}>${inline(m[2])}</h${lvl}>`); i++; continue }
    if (line.startsWith('|')) {
      flush()
      const rows = []
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        const cells = lines[i].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
        if (!cells.every((c) => !c || /^:?-{2,}:?$/.test(c))) rows.push(cells)
        i++
      }
      if (rows.length) {
        const [h, ...body] = rows
        out.push(`<table class="md"><thead><tr>${h.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`)
      }
      continue
    }
    if (/^[-*+]\s+/.test(line) || /^\d+[.)]\s+/.test(line)) {
      flush()
      const ordered = /^\d+[.)]\s+/.test(line)
      const items = []
      while (i < lines.length) {
        const l = lines[i].trim()
        const mm = ordered ? l.match(/^\d+[.)]\s+(.*)/) : l.match(/^[-*+]\s+(.*)/)
        if (!mm) break
        items.push(`<li>${inline(mm[1])}</li>`)
        i++
      }
      out.push(ordered ? `<ol>${items.join('')}</ol>` : `<ul>${items.join('')}</ul>`)
      continue
    }
    para.push(line)
    i++
  }
  flush()
  return out.join('\n')
}

export const countWords = (s) => ((s || '').match(/\b\w+\b/g) || []).length
