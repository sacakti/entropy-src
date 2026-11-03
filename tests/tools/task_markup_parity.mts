// Prints how the browser's parser reads each case, for tests/tools/test_task_markup.py.
import { readFileSync } from 'node:fs'

import { parseBlocks, parseInline, plainText } from '../../frontend/src/features/tools/tasks/markup.ts'

const cases = JSON.parse(readFileSync(process.argv[2], 'utf8')) as { name: string; text: string }[]
const read = cases.map(({ name, text }) => ({
    name,
    blocks: parseBlocks(text),
    inline: parseInline(text),
    plain: plainText(text),
}))
process.stdout.write(JSON.stringify(read))
