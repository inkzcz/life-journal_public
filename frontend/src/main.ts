import { createApp } from 'vue'
import App from './blog/Shell.vue'
import { router } from './blog/router'
import './ui/tokens.css'
import './blog/themes.css'
import {installAppearance} from './ui/theme'
import './style.css'
import './ui/reader.css'
import './ui/studio.css'
import './ui/editor.css'
import './blog/personalization.css'
installAppearance()
createApp(App).use(router).mount('#app')

import './discovery/discovery.css'

import './presentation/typography.css'

import './ui/modern.css'
import './blog/modern-soft.css'

import './blog/appearance.css'
import './blog/garden.css'

import './ui/system.css'
