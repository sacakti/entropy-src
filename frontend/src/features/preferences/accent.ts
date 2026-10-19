/**
 * Readable colors derived from the user's accent for the active theme.
 *
 * The accent is user-chosen, so it can be any color: a lime that works on a
 * dark surface disappears on white, and a dark accent vanishes on black.
 * These helpers keep accent text and labels at WCAG AA contrast (4.5:1).
 */

type Rgb = [number, number, number]

const DARK_INK = '#0b0d10'
const LIGHT_INK = '#ffffff'
const MIN_CONTRAST = 4.5

// Surface each theme draws accent text on (matches theme.css --app-surface).
const SURFACES = {
    dark: '#11151b',
    light: '#ffffff',
} as const

function parseHex(color: string): Rgb | null {
    const match = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color.trim())

    if (!match) return null

    const hex =
        match[1].length === 3
            ? match[1].split('').map((digit) => digit + digit).join('')
            : match[1]

    return [0, 2, 4].map((index) => parseInt(hex.slice(index, index + 2), 16)) as Rgb
}

function toHex([red, green, blue]: Rgb): string {
    return `#${[red, green, blue]
        .map((channel) => Math.round(channel).toString(16).padStart(2, '0'))
        .join('')}`
}

function luminance([red, green, blue]: Rgb): number {
    const [r, g, b] = [red, green, blue].map((channel) => {
        const value = channel / 255
        return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
    })

    return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(first: string, second: string): number {
    const a = parseHex(first)
    const b = parseHex(second)

    if (!a || !b) return 1

    const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (light + 0.05) / (dark + 0.05)
}

function mix(color: Rgb, target: Rgb, amount: number): Rgb {
    return color.map((channel, index) => channel + (target[index] - channel) * amount) as Rgb
}

export interface AccentTokens {
    accent: string
    /** Text/icons drawn on an accent fill (primary buttons, badges). */
    onAccent: string
    /** Accent used as text/icon color on the theme surface. */
    foreground: string
}

export function accentTokens(accent: string, theme: 'dark' | 'light'): AccentTokens {
    const rgb = parseHex(accent)

    if (!rgb) {
        return { accent, onAccent: DARK_INK, foreground: accent }
    }

    const normalized = toHex(rgb)
    const onAccent =
        contrast(normalized, DARK_INK) >= contrast(normalized, LIGHT_INK) ? DARK_INK : LIGHT_INK

    const surface = SURFACES[theme]
    const target: Rgb = theme === 'light' ? [0, 0, 0] : [255, 255, 255]
    let foreground = normalized

    // Move toward black (light theme) or white (dark theme) only as far as needed.
    for (let step = 1; step <= 20 && contrast(foreground, surface) < MIN_CONTRAST; step += 1) {
        foreground = toHex(mix(rgb, target, step * 0.05))
    }

    return { accent: normalized, onAccent, foreground }
}
