import { lazy, Suspense, useState, type ComponentType, type LazyExoticComponent } from 'react'
import { FileDiff, FolderTree, GitCompareArrows, LoaderCircle } from 'lucide-react'

type CompareMode = 'text' | 'file' | 'folder'
const MODES: { id: CompareMode; label: string; icon: typeof GitCompareArrows; component: LazyExoticComponent<ComponentType> }[] = [
    { id: 'text', label: 'Text Compare', icon: GitCompareArrows, component: lazy(() => import('./ContentCompare')) },
    { id: 'file', label: 'File Compare', icon: FileDiff, component: lazy(() => import('./FileCompare')) },
    { id: 'folder', label: 'Folder Compare', icon: FolderTree, component: lazy(() => import('./FolderCompare')) },
]

export default function Clash() {
    const [mode, setMode] = useState<CompareMode>('text')
    const activeMode = MODES.find((item) => item.id === mode) ?? MODES[0]
    const CompareTool = activeMode.component

    return <section className="tools-clash">
        <div className="tools-clash-tabs" role="tablist" aria-label="Compare type">
            {MODES.map(({ id, label, icon: Icon }) => <button
                key={id}
                type="button"
                role="tab"
                id={`clash-tab-${id}`}
                aria-selected={mode === id}
                aria-controls="clash-panel"
                className={mode === id ? 'active' : ''}
                onClick={() => setMode(id)}
            ><Icon size={16} />{label}</button>)}
        </div>
        <div id="clash-panel" role="tabpanel" aria-labelledby={`clash-tab-${mode}`}>
            <Suspense fallback={<div className="tools-empty" role="status"><LoaderCircle size={18} className="entropy-spin" /> Loading compare tool…</div>}>
                <CompareTool />
            </Suspense>
        </div>
    </section>
}
