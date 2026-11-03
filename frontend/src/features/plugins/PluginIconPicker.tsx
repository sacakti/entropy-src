import { pluginsApi, type PluginItem } from '../../api/plugins.api'
import IconPicker from './IconPicker'
import { pluginIcon } from './pluginIcons'

/** A plugin's icon; for those who may edit plugins, a button that opens the collection. */
export default function PluginIconPicker({
    plugin,
    canEdit,
    onChanged,
}: {
    plugin: PluginItem
    canEdit: boolean
    onChanged: (qualifiedName: string, icon: string | null) => void
}) {
    return (
        <IconPicker
            name={plugin.qualified_name}
            noun="plugin"
            icon={plugin.icon}
            glyph={pluginIcon(plugin)}
            canEdit={canEdit}
            onChoose={async (icon) => {
                await pluginsApi.setIcon(plugin.qualified_name, icon)
                onChanged(plugin.qualified_name, icon)
            }}
        />
    )
}
