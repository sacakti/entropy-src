import { lazy, Suspense, useEffect, useState, type ComponentType, type LazyExoticComponent } from 'react'
import { Database, FileDiff, FolderTree, GitCompareArrows } from 'lucide-react'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { isDatabaseCompareHash } from './clashNavigation'

type CompareMode = 'text' | 'file' | 'folder' | 'database'
const MODES: { id: CompareMode; label: string; icon: typeof GitCompareArrows; component: LazyExoticComponent<ComponentType> }[] = [
    { id: 'text', label: 'Text Compare', icon: GitCompareArrows, component: lazy(() => import('./ContentCompare')) },
    { id: 'file', label: 'File Compare', icon: FileDiff, component: lazy(() => import('./FileCompare')) },
    { id: 'folder', label: 'Folder Compare', icon: FolderTree, component: lazy(() => import('./FolderCompare')) },
    { id: 'database', label: 'Database Compare', icon: Database, component: lazy(() => import('./DatabaseCompare')) },
]

export default function Clash() {
    const [mode, setMode] = useState<CompareMode>(() => (isDatabaseCompareHash(window.location.hash) ? 'database' : 'text'))
    const activeMode = MODES.find((item) => item.id === mode) ?? MODES[0]
    const CompareTool = activeMode.component

    // Vision and the bell point here while Clash may already be open on another mode.
    useEffect(() => {
        const follow = () => {
            if (isDatabaseCompareHash(window.location.hash)) setMode('database')
        }
        window.addEventListener('popstate', follow)
        return () => window.removeEventListener('popstate', follow)
    }, [])

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
            <Suspense fallback={<EntropyLoader label="Loading compare tool…" />}>
                <CompareTool />
            </Suspense>
        </div>
    </section>
}
