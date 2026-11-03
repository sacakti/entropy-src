/**
 * The icons a plugin can have, and which one it shows until someone chooses.
 * Adding an icon is adding an entry here.
 */
import {
    Activity,
    AlarmClock,
    Archive,
    ArrowLeftRight,
    BarChart3,
    Bell,
    Bot,
    Boxes,
    Braces,
    Bug,
    Cable,
    ClipboardCheck,
    Cloud,
    CloudUpload,
    Cog,
    Combine,
    Container,
    Cpu,
    Database,
    DatabaseBackup,
    FileCode,
    FileCheck,
    FileSpreadsheet,
    FileText,
    FileWarning,
    Fingerprint,
    Flame,
    FolderSync,
    Gauge,
    GitBranch,
    GitMerge,
    Globe,
    HardDrive,
    HardDriveUpload,
    KeyRound,
    Layers,
    ListChecks,
    Lock,
    Mail,
    Network,
    Package,
    PackageCheck,
    Puzzle,
    Radar,
    RefreshCw,
    Rocket,
    Route,
    SearchCheck,
    SearchCode,
    Send,
    Server,
    ServerCog,
    Shield,
    ShieldCheck,
    Ship,
    Sparkles,
    SquareTerminal,
    Table2,
    Terminal,
    Timer,
    Upload,
    Warehouse,
    Workflow,
    Wrench,
    Zap,
    type LucideIcon,
} from 'lucide-react'

export type PluginIconChoice = { id: string; label: string; icon: LucideIcon }

function choice(id: string, label: string, icon: LucideIcon): PluginIconChoice {
    return { id, label, icon }
}

export const PLUGIN_ICON_GROUPS: { title: string; icons: PluginIconChoice[] }[] = [
    {
        title: 'Deployment',
        icons: [
            choice('rocket', 'Rocket', Rocket),
            choice('ship', 'Ship', Ship),
            choice('package', 'Package', Package),
            choice('package-check', 'Package check', PackageCheck),
            choice('layers', 'Layers', Layers),
            choice('boxes', 'Boxes', Boxes),
            choice('combine', 'Combine', Combine),
            choice('cloud-upload', 'Cloud upload', CloudUpload),
            choice('upload', 'Upload', Upload),
        ],
    },
    {
        title: 'Containers and servers',
        icons: [
            choice('container', 'Container', Container),
            choice('warehouse', 'Registry', Warehouse),
            choice('server', 'Server', Server),
            choice('server-cog', 'Server settings', ServerCog),
            choice('cloud', 'Cloud', Cloud),
            choice('cpu', 'CPU', Cpu),
            choice('hard-drive', 'Disk', HardDrive),
        ],
    },
    {
        title: 'Data',
        icons: [
            choice('database', 'Database', Database),
            choice('database-backup', 'Database backup', DatabaseBackup),
            choice('table', 'Table', Table2),
            choice('file-spreadsheet', 'Spreadsheet', FileSpreadsheet),
            choice('archive', 'Archive', Archive),
        ],
    },
    {
        title: 'Network and transfer',
        icons: [
            choice('network', 'Network', Network),
            choice('globe', 'Globe', Globe),
            choice('route', 'Route', Route),
            choice('cable', 'Cable', Cable),
            choice('transfer', 'Transfer', ArrowLeftRight),
            choice('hard-drive-upload', 'Remote copy', HardDriveUpload),
            choice('folder-sync', 'Folder sync', FolderSync),
            choice('refresh', 'Refresh', RefreshCw),
            choice('send', 'Send', Send),
            choice('mail', 'Mail', Mail),
        ],
    },
    {
        title: 'Security',
        icons: [
            choice('shield', 'Shield', Shield),
            choice('shield-check', 'Shield check', ShieldCheck),
            choice('key', 'Key', KeyRound),
            choice('lock', 'Lock', Lock),
            choice('fingerprint', 'Fingerprint', Fingerprint),
            choice('flame', 'Firewall', Flame),
        ],
    },
    {
        title: 'Monitoring and checks',
        icons: [
            choice('activity', 'Activity', Activity),
            choice('gauge', 'Gauge', Gauge),
            choice('bar-chart', 'Chart', BarChart3),
            choice('radar', 'Radar', Radar),
            choice('bell', 'Bell', Bell),
            choice('timer', 'Timer', Timer),
            choice('alarm', 'Alarm', AlarmClock),
            choice('list-checks', 'Checklist', ListChecks),
            choice('clipboard-check', 'Audit', ClipboardCheck),
            choice('search-check', 'Inspect', SearchCheck),
            choice('search-code', 'Code analysis', SearchCode),
            choice('file-check', 'File check', FileCheck),
            choice('file-warning', 'File warning', FileWarning),
            choice('bug', 'Bug', Bug),
        ],
    },
    {
        title: 'Code and automation',
        icons: [
            choice('terminal', 'Terminal', Terminal),
            choice('square-terminal', 'Console', SquareTerminal),
            choice('file-code', 'Code file', FileCode),
            choice('file-text', 'Text file', FileText),
            choice('braces', 'Braces', Braces),
            choice('git-branch', 'Git branch', GitBranch),
            choice('git-merge', 'Git merge', GitMerge),
            choice('workflow', 'Workflow', Workflow),
            choice('bot', 'Bot', Bot),
            choice('sparkles', 'Sparkles', Sparkles),
            choice('zap', 'Zap', Zap),
            choice('wrench', 'Wrench', Wrench),
            choice('cog', 'Cog', Cog),
            choice('puzzle', 'Puzzle', Puzzle),
        ],
    },
]

const ICONS = new Map(PLUGIN_ICON_GROUPS.flatMap((group) => group.icons).map((item) => [item.id, item.icon]))

/** Until someone chooses: what suits a bundled plugin, then its namespace. */
const PLUGIN_DEFAULTS: Record<string, string> = {
    'builtin.git': 'git-branch',
    'builtin.hello': 'sparkles',
    'builtin.process_monitor': 'cpu',
    'builtin.shell': 'terminal',
    'consolidate.cm_secret': 'key',
    'consolidate.db_scripts': 'database',
    'consolidate.deployment': 'rocket',
    'consolidate.images': 'container',
    'custom.cache_refresh': 'refresh',
    'custom.firewall_xl': 'flame',
    'custom.image_transfer': 'transfer',
    'custom.load_data': 'database-backup',
    'custom.sftp': 'hard-drive-upload',
    'custom.stage_release_copy': 'folder-sync',
    'custom.trd_mig': 'combine',
    'docker.build': 'package',
    'docker.clean': 'archive',
    'docker.docker_file_from_image_change': 'file-code',
    'oc.audit': 'clipboard-check',
    'oc.cm_secret_update': 'key',
    'oc.deployment': 'rocket',
    'oc.pod_metrics': 'activity',
    'oc.rsync': 'refresh',
    'oc.services_routes': 'route',
    'oc.sync_yamls': 'folder-sync',
    'release.context_builder': 'package-check',
    'sqlplus.analyse': 'search-code',
    'sqlplus.invalid_objects_report': 'file-warning',
    'sqlplus.post_validation': 'list-checks',
}

const NAMESPACE_DEFAULTS: Record<string, string> = {
    builtin: 'cog',
    consolidate: 'combine',
    custom: 'wrench',
    docker: 'container',
    oc: 'ship',
    quay: 'warehouse',
    release: 'package-check',
    skopeo: 'search-check',
    sqlplus: 'database',
}

const FALLBACK = 'package'

export function defaultPluginIconId(namespace: string, qualifiedName: string): string {
    return PLUGIN_DEFAULTS[qualifiedName] ?? NAMESPACE_DEFAULTS[namespace] ?? FALLBACK
}

/** A chosen icon, if this browser knows it. */
export function iconById(id: string | null | undefined): LucideIcon | undefined {
    return id ? ICONS.get(id) : undefined
}

/** The icon to draw: the chosen one if this browser knows it, else the default. */
export function pluginIcon(plugin: { namespace: string; qualified_name: string; icon?: string | null }): LucideIcon {
    return (
        (plugin.icon ? ICONS.get(plugin.icon) : undefined) ??
        ICONS.get(defaultPluginIconId(plugin.namespace, plugin.qualified_name)) ??
        Package
    )
}
