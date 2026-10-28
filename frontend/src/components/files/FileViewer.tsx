import { useEffect, type ReactNode } from 'react'
import { Download, X } from 'lucide-react'

import AppPortal from '../layout/AppPortal'
import FilePreview, { type ArchiveBrowse } from './FilePreview'
import '../../styles/file-viewer.css'

/** A file opened over the page; Esc or a click outside closes it. */
export default function FileViewer({ name, details, url, previewUrl, downloadUrl, browse, onClose }: {
    name: string
    details?: ReactNode
    url: string
    previewUrl?: string
    downloadUrl?: string
    browse?: ArchiveBrowse
    onClose: () => void
}) {
    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'Escape' && !document.querySelector('.entropy-modal-backdrop')) onClose()
        }
        document.addEventListener('keydown', onKey)
        return () => document.removeEventListener('keydown', onKey)
    }, [onClose])

    return (
        <AppPortal>
            <div className="file-viewer" role="dialog" aria-modal="true" aria-label={`File: ${name}`} onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
                <div className="file-viewer-frame">
                    <header>
                        <span className="file-viewer-title">
                            <strong title={name}>{name}</strong>
                            {details && <small>{details}</small>}
                        </span>
                        {downloadUrl && (
                            <a className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" href={downloadUrl} download={name} aria-label={`Download ${name}`} title="Download">
                                <Download size={15} />
                            </a>
                        )}
                        <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" onClick={onClose} aria-label="Close viewer" title="Close (Esc)">
                            <X size={16} />
                        </button>
                    </header>
                    <div className="file-viewer-body">
                        <FilePreview name={name} url={url} previewUrl={previewUrl} browse={browse} />
                    </div>
                </div>
            </div>
        </AppPortal>
    )
}
