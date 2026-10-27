import { createElement } from 'react'

import { typeIcon } from './model'

/** The icon of a task type (bug, story, epic, ...). */
export default function TypeIcon({ type, size = 13 }: { type: string; size?: number }) {
    return createElement(typeIcon(type), { size, 'aria-hidden': true })
}
