import { useRef, useState } from 'react'
import { Download, FileCode, FileText, LoaderCircle } from 'lucide-react'

import { runsApi } from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import FloatingMenu from '../../components/layout/FloatingMenu'

/** Downloads the run's report, as a web page or a PDF. */
export default function RunReportButton({ runId, target }: { runId: number; target: string }) {
    const { notify } = useFeedback()
    const [open, setOpen] = useState(false)
    const [busy, setBusy] = useState(false)
    const triggerRef = useRef<HTMLButtonElement>(null)

    const download = async (format: 'html' | 'pdf') => {
        setOpen(false)
        setBusy(true)
        try {
            await runsApi.downloadReport(runId, target, format)
        } catch (cause) {
            notify.error(cause instanceof Error ? cause.message : 'The report was not created.', {
                title: 'Download failed',
            })
        } finally {
            setBusy(false)
        }
    }

    return (
        <>
            <button
                ref={triggerRef}
                type="button"
                className="entropy-button entropy-button-secondary"
                aria-haspopup="menu"
                aria-expanded={open}
                disabled={busy}
                onClick={() => setOpen((value) => !value)}
            >
                {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Download size={15} />} Report
            </button>
            <FloatingMenu
                anchorRef={triggerRef}
                open={open}
                onClose={() => setOpen(false)}
                className="plugins-operation-menu"
            >
                <button type="button" role="menuitem" onClick={() => void download('html')}>
                    <FileCode size={15} aria-hidden="true" /> Download HTML
                </button>
                <button type="button" role="menuitem" onClick={() => void download('pdf')}>
                    <FileText size={15} aria-hidden="true" /> Download PDF
                </button>
            </FloatingMenu>
        </>
    )
}
