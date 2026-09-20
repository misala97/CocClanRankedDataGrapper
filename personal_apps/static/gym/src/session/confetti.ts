/**
 * The record takeover's confetti. Forty-six rectangles with gravity, drag and
 * spin, drawn on one canvas for about a second.
 *
 * No library. canvas-confetti is 12 kB for a particle loop this file states in
 * forty lines, and it ships its own colour defaults -- the particles here are
 * read from the app's own tokens at burst time, so they follow the theme and
 * read as this screen celebrating rather than as a plugin dropped onto it.
 */

interface Particle {
  x: number; y: number; vx: number; vy: number
  w: number; h: number; rot: number; vr: number
  colour: string; life: number; max: number
}

/** --record is the obvious one; --done and --live are the other two fills this
 *  screen already uses, so the burst cannot introduce a colour the palette
 *  does not have. --record twice: it is what the moment is about. */
const TOKENS = ['--record', '--done', '--live', '--record']

export interface Burst {
  x: number
  y: number
  count: number
  /** Radians of scatter around the aim. */
  spread: number
  /** Radians off straight-up. Negative is left. */
  aim: number
}

export function readPalette(root: HTMLElement = document.documentElement): string[] {
  const style = getComputedStyle(root)
  return TOKENS.map((name) => style.getPropertyValue(name).trim()).filter(Boolean)
}

/**
 * Runs one burst set to completion on `canvas`, then clears it.
 *
 * Returns a stop function: the takeover can be dismissed early, and a loop
 * still drawing over a panel the user is using again is the one way this
 * could become annoying rather than fun.
 */
export function play(canvas: HTMLCanvasElement, bursts: Burst[]): () => void {
  const ctx = canvas.getContext('2d')
  if (ctx === null) return () => {}

  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  // Set the backing store from the CSS box, and never the other way round: a
  // canvas is a REPLACED element, so `inset: 0` alone does not size it and
  // each pass would read back the box it had just written, doubling it.
  canvas.width = Math.round(rect.width * dpr)
  canvas.height = Math.round(rect.height * dpr)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  const colours = readPalette()
  let parts: Particle[] = []
  for (const burst of bursts) {
    for (let i = 0; i < burst.count; i += 1) {
      const angle = -Math.PI / 2 + burst.aim + (Math.random() - 0.5) * burst.spread
      const speed = 5.5 + Math.random() * 7.5
      parts.push({
        x: burst.x, y: burst.y,
        vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
        w: 4 + Math.random() * 5, h: 7 + Math.random() * 7,
        rot: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 0.4,
        colour: colours[Math.floor(Math.random() * colours.length)] ?? '#F0B429',
        life: 0, max: 62 + Math.random() * 30,
      })
    }
  }

  let frame = 0
  const step = () => {
    ctx.clearRect(0, 0, rect.width, rect.height)
    parts = parts.filter((p) => p.life < p.max)
    for (const p of parts) {
      p.life += 1
      p.vy += 0.36
      p.vx *= 0.99
      p.vy *= 0.995
      p.x += p.vx
      p.y += p.vy
      p.rot += p.vr
      ctx.save()
      // Cubed, so the fade happens at the END of the flight rather than
      // dimming the burst from the first frame.
      ctx.globalAlpha = Math.max(0, 1 - (p.life / p.max) ** 3)
      ctx.translate(p.x, p.y)
      ctx.rotate(p.rot)
      ctx.fillStyle = p.colour
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h)
      ctx.restore()
    }
    frame = parts.length > 0 ? requestAnimationFrame(step) : 0
    if (frame === 0) ctx.clearRect(0, 0, rect.width, rect.height)
  }
  frame = requestAnimationFrame(step)

  return () => {
    if (frame !== 0) cancelAnimationFrame(frame)
    frame = 0
    parts = []
    ctx.clearRect(0, 0, rect.width, rect.height)
  }
}
