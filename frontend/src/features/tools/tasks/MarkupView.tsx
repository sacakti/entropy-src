import type { ReactNode } from 'react'

import { MentionText } from './MentionInput'
import { parseBlocks, parseInline, type Block } from './markup'
import type { Member } from './model'

function Inline({ text, members }: { text: string; members: Member[] }) {
    return parseInline(text).map((run, index) => {
        let node: ReactNode = run.code ? (
            <code className="task-inline-code">{run.text}</code>
        ) : (
            <MentionText text={run.text} members={members} />
        )
        if (run.strike) node = <s>{node}</s>
        if (run.italic) node = <em>{node}</em>
        if (run.bold) node = <strong>{node}</strong>
        return <span key={index}>{node}</span>
    })
}

function BlockView({ block, members, onToggle, attachment }: {
    block: Block
    members: Member[]
    onToggle?: (line: number) => void
    attachment: (id: number, caption: string) => ReactNode
}) {
    switch (block.type) {
        case 'heading': {
            const Tag = `h${block.level + 2}` as 'h3' | 'h4' | 'h5'
            return <Tag className={`task-md-h${block.level}`}><Inline text={block.text} members={members} /></Tag>
        }
        case 'paragraph':
            return <p className="task-md-p"><Inline text={block.text} members={members} /></p>
        case 'code':
            return <pre className="task-md-code">{block.text}</pre>
        case 'attachment':
            return attachment(block.id, block.caption)
        case 'table':
            return (
                <div className="task-md-table">
                    <table>
                        <thead>
                            <tr>{block.header.map((cell, index) => <th key={index} scope="col"><Inline text={cell} members={members} /></th>)}</tr>
                        </thead>
                        <tbody>
                            {block.rows.map((row, rowIndex) => (
                                <tr key={rowIndex}>{row.map((cell, index) => <td key={index}><Inline text={cell} members={members} /></td>)}</tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )
        case 'list': {
            const Tag = block.ordered ? 'ol' : 'ul'
            const tasks = block.items.every((item) => item.checked !== null)
            return (
                <Tag className={`task-md-list${tasks ? ' is-checklist' : ''}`} start={block.ordered ? block.start : undefined}>
                    {block.items.map((item) => (
                        <li
                            key={item.line}
                            className={item.checked === null ? undefined : 'is-task'}
                            style={item.indent ? { marginLeft: `${item.indent * 18}px` } : undefined}
                        >
                            {item.checked !== null && (
                                <input
                                    type="checkbox"
                                    className="list-check"
                                    checked={item.checked}
                                    disabled={!onToggle}
                                    aria-label={`Mark "${item.text}" as ${item.checked ? 'not done' : 'done'}`}
                                    onChange={() => onToggle?.(item.line)}
                                />
                            )}
                            <span className={item.checked ? 'is-done' : undefined}>
                                <Inline text={item.text} members={members} />
                            </span>
                        </li>
                    ))}
                </Tag>
            )
        }
    }
}

/** A description as it reads; with `onToggle`, its checklist items can be ticked here. */
export default function MarkupView({ text, members, onToggle, attachment }: {
    text: string
    members: Member[]
    onToggle?: (line: number) => void
    /** How an attachment in the text is shown. */
    attachment: (id: number, caption: string) => ReactNode
}) {
    return (
        <div className="task-description">
            {parseBlocks(text).map((block, index) => (
                <BlockView key={index} block={block} members={members} onToggle={onToggle} attachment={attachment} />
            ))}
        </div>
    )
}
