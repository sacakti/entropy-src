import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { Circle, Copy, LoaderCircle, MoveUpRight, Pencil, RectangleHorizontal, Replace, Slash, Trash2, Undo2, X } from 'lucide-react'

type Tool = 'pen' | 'line' | 'arrow' | 'ellipse' | 'rect'
type Point = { x: number; y: number }
// Points are in the image's own pixels, so the saved file matches what was drawn.
type Shape = { tool: Tool; color: string; width: number; points: Point[] }

const TOOLS: { id: Tool; label: string; icon: typeof Pencil }[] = [
    { id: 'ellipse', label: 'Circle', icon: Circle },
    { id: 'rect', label: 'Box', icon: RectangleHorizontal },
    { id: 'line', label: 'Line', icon: Slash },
    { id: 'arrow', label: 'Arrow', icon: MoveUpRight },
    { id: 'pen', label: 'Draw', icon: Pencil },
]
const COLORS = ['#e5383b', '#f7b801', '#2ec27e', '#3584e4', '#ffffff', '#000000']
const WIDTHS = [{ id: 1, label: 'Thin' }, { id: 2, label: 'Medium' }, { id: 4, label: 'Thick' }]

function draw(context: CanvasRenderingContext2D, shape: Shape) {
    const [start] = shape.points
    const end = shape.points[shape.points.length - 1]
    if (!start || !end) return
    context.strokeStyle = shape.color
    context.lineWidth = shape.width
    context.lineCap = 'round'
    context.lineJoin = 'round'
    context.beginPath()
    if (shape.tool === 'pen') {
        context.moveTo(start.x, start.y)
        shape.points.forEach((point) => context.lineTo(point.x, point.y))
    } else if (shape.tool === 'line' || shape.tool === 'arrow') {
        context.moveTo(start.x, start.y)
        context.lineTo(end.x, end.y)
        if (shape.tool === 'arrow') {
            const angle = Math.atan2(end.y - start.y, end.x - start.x)
            const head = shape.width * 4
            for (const side of [-1, 1]) {
                context.moveTo(end.x, end.y)
                context.lineTo(end.x - head * Math.cos(angle + side * Math.PI / 7), end.y - head * Math.sin(angle + side * Math.PI / 7))
            }
        }
    } else if (shape.tool === 'rect') {
        context.rect(start.x, start.y, end.x - start.x, end.y - start.y)
    } else {
        // The circle fills the dragged box, so it can be stretched around anything.
        const rx = Math.abs(end.x - start.x) / 2
        const ry = Math.abs(end.y - start.y) / 2
        context.ellipse((start.x + end.x) / 2, (start.y + end.y) / 2, rx, ry, 0, 0, Math.PI * 2)
    }
    context.stroke()
}

export default function ImageMarkup({ source, filename, onCancel, onSave, onReplace }: {
    source: string
    filename: string
    onCancel: () => void
    onSave: (file: File) => Promise<boolean>
    // Missing when the user may not remove the original.
    onReplace?: (file: File) => Promise<boolean>
}) {
    const frame = useRef<HTMLDivElement>(null)
    const canvas = useRef<HTMLCanvasElement>(null)
    const image = useRef<HTMLImageElement | null>(null)
    const [natural, setNatural] = useState<{ width: number; height: number } | null>(null)
    const [fit, setFit] = useState({ width: 0, height: 0 })
    const [tool, setTool] = useState<Tool>('ellipse')
    const [color, setColor] = useState(COLORS[0])
    const [weight, setWeight] = useState(2)
    const [shapes, setShapes] = useState<Shape[]>([])
    const [drawing, setDrawing] = useState<Shape | null>(null)
    const [saving, setSaving] = useState<'copy' | 'replace' | null>(null)

    useEffect(() => {
        const element = new Image()
        element.onload = () => {
            image.current = element
            setNatural({ width: element.naturalWidth || 800, height: element.naturalHeight || 600 })
        }
        element.src = source
    }, [source])

    // Fit the image into the space left by the toolbar, never enlarging it.
    useEffect(() => {
        const element = frame.current
        if (!element || !natural) return
        const measure = () => {
            const style = getComputedStyle(element)
            const width = element.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
            const height = element.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom)
            const scale = Math.max(0, Math.min(width / natural.width, height / natural.height, 1))
            setFit({ width: Math.floor(natural.width * scale), height: Math.floor(natural.height * scale) })
        }
        measure()
        const observer = new ResizeObserver(measure)
        observer.observe(element)
        return () => observer.disconnect()
    }, [natural])

    useEffect(() => {
        const context = canvas.current?.getContext('2d')
        if (!context || !natural) return
        context.clearRect(0, 0, natural.width, natural.height)
        ;[...shapes, ...(drawing ? [drawing] : [])].forEach((shape) => draw(context, shape))
    }, [shapes, drawing, natural])

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (document.querySelector('.entropy-modal-backdrop, .entropy-dialog-backdrop')) return
            if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z') {
                event.preventDefault()
                setShapes((current) => current.slice(0, -1))
            }
        }
        document.addEventListener('keydown', onKey)
        return () => document.removeEventListener('keydown', onKey)
    }, [])

    const point = (event: ReactPointerEvent<HTMLCanvasElement>): Point => {
        const rect = event.currentTarget.getBoundingClientRect()
        return {
            x: ((event.clientX - rect.left) / rect.width) * (natural?.width ?? 1),
            y: ((event.clientY - rect.top) / rect.height) * (natural?.height ?? 1),
        }
    }
    // Stroke widths follow the image size, so marks look the same on any screenshot.
    const strokeWidth = natural ? Math.max(2, Math.round(Math.max(natural.width, natural.height) / 400)) * weight : weight

    const save = async (mode: 'copy' | 'replace') => {
        if (!natural || !image.current) return
        const output = document.createElement('canvas')
        output.width = natural.width
        output.height = natural.height
        const context = output.getContext('2d')
        if (!context) return
        context.drawImage(image.current, 0, 0, natural.width, natural.height)
        shapes.forEach((shape) => draw(context, shape))
        setSaving(mode)
        try {
            const blob = await new Promise<Blob | null>((resolve) => output.toBlob(resolve, 'image/png'))
            if (!blob) return
            // Marks are saved as PNG; a replacement keeps the original's name.
            const base = filename.replace(/\.[^.]+$/, '')
            const file = new File([blob], mode === 'copy' ? `${base}-marked.png` : `${base}.png`, { type: 'image/png' })
            const saved = mode === 'copy' ? await onSave(file) : await onReplace?.(file)
            if (saved) onCancel()
        } finally {
            setSaving(null)
        }
    }

    return (
        <div className="task-markup">
            <div className="task-markup-tools" role="toolbar" aria-label="Markup tools">
                <span className="task-markup-group">
                    {TOOLS.map(({ id, label, icon: Icon }) => (
                        <button key={id} type="button" className={`entropy-button entropy-button-ghost entropy-button-sm${tool === id ? ' is-active' : ''}`} onClick={() => setTool(id)} aria-pressed={tool === id} title={label}>
                            <Icon size={15} /> <span>{label}</span>
                        </button>
                    ))}
                </span>
                <span className="task-markup-group">
                    {COLORS.map((value) => (
                        <button key={value} type="button" className={`task-markup-color${color === value ? ' is-active' : ''}`} style={{ background: value }} onClick={() => setColor(value)} aria-label={`Colour ${value}`} aria-pressed={color === value} />
                    ))}
                </span>
                <select className="entropy-select task-markup-width" value={weight} onChange={(event) => setWeight(Number(event.target.value))} aria-label="Line thickness">
                    {WIDTHS.map((width) => <option key={width.id} value={width.id}>{width.label}</option>)}
                </select>
                <span className="task-markup-group">
                    <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" onClick={() => setShapes(shapes.slice(0, -1))} disabled={!shapes.length} aria-label="Undo" title="Undo (Ctrl+Z / ⌘Z)"><Undo2 size={15} /></button>
                    <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" onClick={() => setShapes([])} disabled={!shapes.length} aria-label="Clear all marks" title="Clear all marks"><Trash2 size={15} /></button>
                </span>
                <span className="task-markup-group is-end">
                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={onCancel} disabled={saving !== null}><X size={15} /> Cancel</button>
                    <button type="button" className={`entropy-button entropy-button-${onReplace ? 'secondary' : 'primary'} entropy-button-sm`} onClick={() => void save('copy')} disabled={saving !== null || !shapes.length} title={`Attach as ${filename.replace(/\.[^.]+$/, '')}-marked.png; the original is kept`}>
                        {saving === 'copy' ? <LoaderCircle size={15} className="entropy-spin" /> : <Copy size={15} />} Save a copy
                    </button>
                    {onReplace && (
                        <button type="button" className="entropy-button entropy-button-primary entropy-button-sm" onClick={() => void save('replace')} disabled={saving !== null || !shapes.length} title="Replace the original with the marked-up image">
                            {saving === 'replace' ? <LoaderCircle size={15} className="entropy-spin" /> : <Replace size={15} />} Replace
                        </button>
                    )}
                </span>
            </div>
            <div className="task-markup-stage" ref={frame}>
                {!natural ? (
                    <LoaderCircle size={22} className="entropy-spin" aria-label="Loading" />
                ) : (
                    <div className="task-markup-canvas" style={{ width: fit.width, height: fit.height }}>
                        <img src={source} alt={filename} draggable={false} />
                        <canvas
                            ref={canvas}
                            width={natural.width}
                            height={natural.height}
                            onPointerDown={(event) => {
                                event.currentTarget.setPointerCapture(event.pointerId)
                                setDrawing({ tool, color, width: strokeWidth, points: [point(event)] })
                            }}
                            onPointerMove={(event) => {
                                if (!drawing) return
                                const next = point(event)
                                setDrawing({ ...drawing, points: drawing.tool === 'pen' ? [...drawing.points, next] : [drawing.points[0], next] })
                            }}
                            onPointerUp={() => {
                                if (drawing && drawing.points.length > 1) setShapes([...shapes, drawing])
                                setDrawing(null)
                            }}
                            onPointerCancel={() => setDrawing(null)}
                        />
                    </div>
                )}
            </div>
        </div>
    )
}
