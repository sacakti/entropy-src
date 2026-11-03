// What the editor's toolbar and keys do to the text; run by tests/tools/test_task_markup.py.
import assert from 'node:assert/strict'

const edit = await import(process.argv[2])
const {
    addTableColumn, addTableRow, continueBlock, indentList, insertTable, lineStyleAt, moveCell,
    removeTableColumn, removeTableRow, setLineStyle, tableAt, toggleCheckbox, toggleInline,
} = edit

const selected = (result: { text: string; start: number; end: number }) => result.text.slice(result.start, result.end)

// Inline styles wrap the selection, and take it away again.
let result = toggleInline('a word here', 2, 6, '**')
assert.equal(result.text, 'a **word** here')
assert.equal(selected(result), '**word**')
assert.equal(toggleInline(result.text, result.start, result.end, '**').text, 'a word here')
assert.equal(toggleInline('a **word** here', 4, 8, '**').text, 'a word here')
result = toggleInline('ab', 1, 1, '~~')
assert.equal(result.text, 'a~~~~b')
assert.equal(result.start, 3)
assert.equal(toggleInline('one\n\ntwo', 0, 8, '*').text, '*one*\n\n*two*')
assert.equal(toggleInline('  padded  ', 0, 10, '**').text, '  **padded**  ')
// Italic inside bold is added, not mistaken for bold's marker.
assert.equal(toggleInline('**word**', 2, 6, '*').text, '***word***')
assert.equal(toggleInline('*word*', 1, 5, '*').text, 'word')

// Line styles.
assert.equal(setLineStyle('text', 0, 0, 'h1').text, '# text')
assert.equal(setLineStyle('# text', 0, 0, 'h2').text, '## text')
assert.equal(setLineStyle('## text', 0, 0, 'paragraph').text, 'text')
assert.equal(setLineStyle('one\ntwo', 0, 7, 'bullet').text, '- one\n- two')
assert.equal(setLineStyle('one\ntwo', 0, 7, 'number').text, '1. one\n2. two')
assert.equal(setLineStyle('one\n\ntwo', 0, 8, 'check').text, '- [ ] one\n\n- [ ] two')
assert.equal(setLineStyle('- one', 0, 0, 'bullet').text, 'one')
assert.equal(setLineStyle('- one', 0, 0, 'check').text, '- [ ] one')
assert.equal(setLineStyle('- [ ] one', 0, 0, 'number').text, '1. one')
assert.equal(setLineStyle('', 0, 0, 'check').text, '- [ ] ')
assert.equal(setLineStyle('a\nb', 2, 2, 'h3').text, 'a\n### b')
assert.equal(lineStyleAt('a\n## b', 3), 'h2')
assert.equal(lineStyleAt('- [x] a', 0), 'check')
assert.equal(lineStyleAt('1. a', 0), 'number')
assert.equal(lineStyleAt('- a', 0), 'bullet')
assert.equal(lineStyleAt('a', 0), 'paragraph')

// A new table sits apart from the text, with its first heading selected.
result = insertTable('before', 6, 6, 1, 2)
assert.equal(result.text, 'before\n\n| Column 1 | Column 2 |\n| --- | --- |\n|   |   |\n')
assert.equal(selected(result), 'Column 1')
assert.equal(insertTable('', 0, 0, 1, 1).text, '| Column 1 |\n| --- |\n|   |\n')
assert.equal(insertTable('a\n\nb', 2, 2, 1, 1).text.startsWith('a\n\n| Column 1'), true)

const TABLE = 'x\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\ny'
const at = (text: string, part: string) => text.indexOf(part) + 1
assert.equal(tableAt(TABLE, 0), null)
assert.equal(tableAt('a | b\nno rule', 0), null)
assert.equal(tableAt(TABLE, at(TABLE, '2 |'))?.cell, 1)
assert.equal(tableAt(TABLE, at(TABLE, '2 |'))?.line, 2)

// Tab walks the cells, past the rule line; past the end comes a new row.
result = moveCell(TABLE, at(TABLE, 'A'), false)
assert.equal(selected(result), 'B')
result = moveCell(TABLE, at(TABLE, 'B'), false)
assert.equal(selected(result), '1')
result = moveCell(TABLE, at(TABLE, '1 |'), true)
assert.equal(selected(result), 'B')
assert.equal(moveCell(TABLE, at(TABLE, 'A') - 1, true), null)
result = moveCell(TABLE, at(TABLE, '2 |'), false)
assert.equal(result.text, 'x\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n|   |   |\n\ny')
assert.equal(moveCell('plain', 0, false), null)

// Rows and columns.
assert.equal(addTableRow(TABLE, at(TABLE, 'A')).text, 'x\n\n| A | B |\n| --- | --- |\n|   |   |\n| 1 | 2 |\n\ny')
assert.equal(addTableColumn(TABLE, at(TABLE, 'A')).text, 'x\n\n| A | Column 3 | B |\n| --- | --- | --- |\n| 1 |  | 2 |\n\ny')
assert.equal(removeTableRow(TABLE, at(TABLE, '1 |')).text, 'x\n\n| A | B |\n| --- | --- |\n\ny')
assert.equal(removeTableRow(TABLE, at(TABLE, 'A')), null)
assert.equal(removeTableColumn(TABLE, at(TABLE, 'B')).text, 'x\n\n| A |\n| --- |\n| 1 |\n\ny')
assert.equal(removeTableColumn('| A |\n|---|\n| 1 |', 2), null)

// Enter carries lists and tables on; an empty item ends the list.
const enter = (text: string) => continueBlock(text, text.length)
assert.equal(enter('- one').text, '- one\n- ')
assert.equal(enter('3. three').text, '3. three\n4. ')
assert.equal(enter('- [x] done').text, '- [x] done\n- [ ] ')
assert.equal(enter('  - nested').text, '  - nested\n  - ')
assert.equal(enter('- ').text, '')
assert.equal(enter('a\n- [ ] ').text, 'a\n')
assert.equal(enter('plain'), null)
assert.equal(enter('# heading'), null)
assert.equal(continueBlock(TABLE, at(TABLE, '1 |')).text, 'x\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n|   |   |\n\ny')

// Tab nests list items only.
assert.equal(indentList('- one', 0, 0, false).text, '  - one')
assert.equal(indentList('  - one', 0, 0, true).text, '- one')
assert.equal(indentList('- a\n- b', 0, 7, false).text, '  - a\n  - b')
assert.equal(indentList('plain', 0, 0, false), null)

// Ticking from the view changes just that line, and nothing that only looks similar.
assert.equal(toggleCheckbox('a\n- [ ] b\n- [x] c', 1), 'a\n- [x] b\n- [x] c')
assert.equal(toggleCheckbox('a\n- [ ] b\n- [x] c', 2), 'a\n- [ ] b\n- [ ] c')
assert.equal(toggleCheckbox('see [ ] here', 0), 'see [ ] here')
assert.equal(toggleCheckbox('- [ ] a', 5), '- [ ] a')
