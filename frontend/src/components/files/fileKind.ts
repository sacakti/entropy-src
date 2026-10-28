export type FileKind = 'image' | 'video' | 'audio' | 'pdf' | 'html' | 'csv' | 'sheet' | 'document' | 'legacy' | 'text' | 'archive' | 'other'

const KINDS: [FileKind, RegExp][] = [
    ['image', /\.(png|jpe?g|gif|webp|bmp|svg|ico|avif)$/i],
    ['video', /\.(mp4|webm|ogv|mov|m4v)$/i],
    ['audio', /\.(mp3|wav|ogg|oga|m4a|flac)$/i],
    ['pdf', /\.pdf$/i],
    ['html', /\.x?html?$/i],
    ['csv', /\.(csv|tsv)$/i],
    ['sheet', /\.(xlsx|xlsm)$/i],
    ['document', /\.(docx|docm)$/i],
    // Binary Office formats from before 2007; only their XML successors are previewed.
    ['legacy', /\.(xls|doc|ppt|pptx)$/i],
    ['archive', /\.(zip|jar|war|ear|whl|nupkg|apk|aar)$/i],
    [
        'text',
        /(\.(txt|log|out|err|json|jsonl|ya?ml|xml|md|ini|conf|cfg|properties|env|sh|bash|zsh|ps1|bat|cmd|sql|py|js|mjs|ts|tsx|jsx|css|scss|java|kt|go|rs|rb|php|c|h|cpp|hpp|cs|toml|lock|gradle|tf|tfvars|j2|tpl|diff|patch|pem|crt|manifest|mf)|\/(Dockerfile|Makefile|Jenkinsfile|README|LICENSE|CHANGELOG)[^/]*)$/i,
    ],
]

/** What the file viewer can show for a file, by its name. */
export function fileKind(name: string): FileKind {
    const path = `/${name}`
    return KINDS.find(([, pattern]) => pattern.test(path))?.[0] ?? 'other'
}
