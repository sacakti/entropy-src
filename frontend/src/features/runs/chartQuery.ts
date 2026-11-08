/**
 * The query language of an app chart, run in the browser over the samples the
 * plugin published:
 *
 *   [sum|avg|max|min](metric) [where condition [and condition]...] [top|bottom N]
 *
 * A condition tests the series name (`pod ~ api`, `pod != web-1`; `~` and `!~`
 * are case-insensitive regular expressions) or a series' latest value of any
 * metric (`memory_percent > 80`). top/bottom rank series by their latest value
 * of the charted metric. Examples:
 *
 *   cpu top 5
 *   memory where pod ~ "^api-" and restarts > 0
 *   sum(memory) where pod !~ job
 */

export type Aggregate = 'sum' | 'avg' | 'max' | 'min'
export type Operator = '~' | '!~' | '=' | '!=' | '>' | '>=' | '<' | '<='

export interface Condition {
    field: string
    op: Operator
    value: string | number
}

export interface ChartQuery {
    aggregate: Aggregate | null
    metric: string
    conditions: Condition[]
    order: 'top' | 'bottom'
    /** null: the default number of series. */
    limit: number | null
}

/** Lines one chart shows at most: the palette's eight distinguishable colors. */
export const MAX_SERIES = 8

export interface ChartSample {
    at: string
    /** One value per metric, in the chart's declared order (null: no sample). */
    values: Record<string, (number | null)[]>
}

export interface QueryResult {
    times: string[]
    series: { name: string; points: (number | null)[] }[]
    /** Series that matched but did not fit (beyond top/bottom or MAX_SERIES). */
    hidden: number
}

const AGGREGATES: readonly string[] = ['sum', 'avg', 'max', 'min']
const OPERATORS: readonly Operator[] = ['!~', '>=', '<=', '!=', '~', '=', '>', '<']
const TEXT_OPERATORS: readonly Operator[] = ['~', '!~', '=', '!=']

export class QueryError extends Error {}

// ----------------------------------------------------------------------
// Parsing
// ----------------------------------------------------------------------

class Scanner {
    private position = 0
    private readonly text: string

    constructor(text: string) {
        this.text = text
    }

    private skipSpace(): void {
        while (this.position < this.text.length && /\s/.test(this.text[this.position])) this.position += 1
    }

    done(): boolean {
        this.skipSpace()
        return this.position >= this.text.length
    }

    peekWord(): string | null {
        this.skipSpace()
        const match = /^[A-Za-z_][\w.-]*/.exec(this.text.slice(this.position))
        return match ? match[0] : null
    }

    word(what: string): string {
        const found = this.peekWord()
        if (!found) throw new QueryError(`Expected ${what} at "${this.rest()}".`)
        this.position += found.length
        return found
    }

    take(symbol: string): boolean {
        this.skipSpace()
        if (this.text.startsWith(symbol, this.position)) {
            this.position += symbol.length
            return true
        }
        return false
    }

    operator(): Operator {
        this.skipSpace()
        for (const op of OPERATORS) {
            if (this.text.startsWith(op, this.position)) {
                this.position += op.length
                return op
            }
        }
        throw new QueryError(`Expected an operator (~ !~ = != > >= < <=) at "${this.rest()}".`)
    }

    /** A quoted string, or everything up to the next space. */
    value(): string {
        this.skipSpace()
        const quote = this.text[this.position]
        if (quote === '"' || quote === "'") {
            const end = this.text.indexOf(quote, this.position + 1)
            if (end < 0) throw new QueryError('A quoted value is not closed.')
            const found = this.text.slice(this.position + 1, end)
            this.position = end + 1
            return found
        }
        const match = /^\S+/.exec(this.text.slice(this.position))
        if (!match) throw new QueryError('Expected a value at the end of the query.')
        this.position += match[0].length
        return match[0]
    }

    rest(): string {
        return this.text.slice(this.position).trim() || 'the end'
    }
}

/** Parse a query; QueryError says what is wrong in words. */
export function parseQuery(text: string, metrics: string[], seriesLabel: string): ChartQuery {
    const scanner = new Scanner(text)
    const known = (name: string) => metrics.includes(name)
    const needMetric = (name: string) => {
        if (!known(name)) throw new QueryError(`Unknown metric "${name}". Use one of: ${metrics.join(', ')}.`)
        return name
    }

    let aggregate: Aggregate | null = null
    let metric: string
    const first = scanner.word('a metric')
    if (AGGREGATES.includes(first.toLowerCase()) && scanner.take('(')) {
        aggregate = first.toLowerCase() as Aggregate
        metric = needMetric(scanner.word('a metric'))
        if (!scanner.take(')')) throw new QueryError(`Expected ")" after ${metric}.`)
    } else {
        metric = needMetric(first)
    }

    const conditions: Condition[] = []
    if (scanner.peekWord()?.toLowerCase() === 'where') {
        scanner.word('where')
        do {
            const field = scanner.word('a condition')
            const isName = field === seriesLabel || field === 'name'
            if (!isName) needMetric(field)
            const op = scanner.operator()
            const raw = scanner.value()
            if (isName) {
                if (!TEXT_OPERATORS.includes(op)) throw new QueryError(`${seriesLabel} is compared with ~ !~ = or !=.`)
                if (op === '~' || op === '!~') compile(raw)
                conditions.push({ field: seriesLabel, op, value: raw })
            } else {
                const number = Number(raw)
                if (!Number.isFinite(number)) throw new QueryError(`${field} is compared with a number, not "${raw}".`)
                conditions.push({ field, op, value: number })
            }
        } while (scanner.peekWord()?.toLowerCase() === 'and' && scanner.word('and'))
    }

    let order: ChartQuery['order'] = 'top'
    let limit: number | null = null
    const ranking = scanner.peekWord()?.toLowerCase()
    if (ranking === 'top' || ranking === 'bottom') {
        scanner.word(ranking)
        order = ranking
        const count = Number(scanner.value())
        if (!Number.isInteger(count) || count < 1) throw new QueryError(`${ranking} needs a whole number of series.`)
        limit = Math.min(count, MAX_SERIES)
    }

    if (!scanner.done()) throw new QueryError(`Unexpected "${scanner.rest()}".`)
    return { aggregate, metric, conditions, order, limit }
}

function compile(pattern: string): RegExp {
    try {
        return new RegExp(pattern, 'i')
    } catch {
        throw new QueryError(`"${pattern}" is not a valid pattern.`)
    }
}

const quote = (value: string) => (/^[^\s"']+$/.test(value) ? value : `"${value.replace(/"/g, '')}"`)

/** The text of a query, as the user would write it. */
export function formatQuery(query: ChartQuery): string {
    const parts = [query.aggregate ? `${query.aggregate}(${query.metric})` : query.metric]
    if (query.conditions.length) {
        parts.push(
            'where',
            query.conditions
                .map((item) => `${item.field} ${item.op} ${typeof item.value === 'number' ? item.value : quote(item.value)}`)
                .join(' and '),
        )
    }
    if (query.limit !== null) parts.push(query.order, String(query.limit))
    return parts.join(' ')
}

/** A text filter as a pattern that matches it literally. */
export const literalPattern = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// ----------------------------------------------------------------------
// Running
// ----------------------------------------------------------------------

function latest(samples: ChartSample[], series: string, index: number): number | null {
    for (let position = samples.length - 1; position >= 0; position -= 1) {
        const value = samples[position].values[series]?.[index]
        if (value !== null && value !== undefined) return value
    }
    return null
}

function test(condition: Condition, name: string, value: () => number | null): boolean {
    if (typeof condition.value === 'string') {
        const text = condition.value
        if (condition.op === '~') return compile(text).test(name)
        if (condition.op === '!~') return !compile(text).test(name)
        if (condition.op === '=') return name === text
        return name !== text
    }
    const found = value()
    if (found === null) return false
    const wanted = condition.value
    switch (condition.op) {
        case '>': return found > wanted
        case '>=': return found >= wanted
        case '<': return found < wanted
        case '<=': return found <= wanted
        case '=': return found === wanted
        case '!=': return found !== wanted
        default: return false
    }
}

function combine(aggregate: Aggregate, values: number[]): number | null {
    if (!values.length) return null
    if (aggregate === 'sum') return values.reduce((total, value) => total + value, 0)
    if (aggregate === 'avg') return values.reduce((total, value) => total + value, 0) / values.length
    if (aggregate === 'max') return Math.max(...values)
    return Math.min(...values)
}

export function runQuery(query: ChartQuery, metrics: string[], samples: ChartSample[]): QueryResult {
    const index = metrics.indexOf(query.metric)
    const names = new Set<string>()
    samples.forEach((sample) => Object.keys(sample.values).forEach((name) => names.add(name)))

    const matching = [...names].filter((name) =>
        query.conditions.every((condition) =>
            test(condition, name, () => latest(samples, name, metrics.indexOf(condition.field))),
        ),
    )
    // Rank by the latest value; series with none go last either way.
    const ranked = matching
        .map((name) => ({ name, value: latest(samples, name, index) }))
        .sort((left, right) => {
            if (left.value === null || right.value === null) return left.value === null ? 1 : -1
            return query.order === 'top' ? right.value - left.value : left.value - right.value
        })
        .map((item) => item.name)

    const times = samples.map((sample) => sample.at)
    const pointsOf = (name: string) => samples.map((sample) => sample.values[name]?.[index] ?? null)

    if (query.aggregate) {
        const chosen = query.limit !== null ? ranked.slice(0, query.limit) : ranked
        const aggregate = query.aggregate
        const points = samples.map((sample) =>
            combine(
                aggregate,
                chosen
                    .map((name) => sample.values[name]?.[index])
                    .filter((value): value is number => value !== null && value !== undefined),
            ),
        )
        return { times, series: [{ name: `${aggregate}(${query.metric})`, points }], hidden: 0 }
    }

    const shown = ranked.slice(0, query.limit ?? MAX_SERIES)
    return {
        times,
        series: shown.map((name) => ({ name, points: pointsOf(name) })),
        hidden: ranked.length - shown.length,
    }
}
