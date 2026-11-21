import { createRouter,createWebHistory } from 'vue-router'
import { request } from '../api'
export function safeReturn(value:unknown){return typeof value==='string'&&value.startsWith('/')&&!value.startsWith('//')&&!/[\\\x00-\x1f]/.test(value)&&!value.startsWith('/login')?value:'/'}
export const router=createRouter({history:createWebHistory(),routes:[
 {path:'/login',component:()=>import('./LoginPage.vue')},
 {path:'/setup',component:()=>import('../setup/SetupPage.vue')},
 {path:'/journals',redirect:'/stories'},
 {path:'/admin/system',component:()=>import('../setup/SystemPage.vue')},
 {path:'/admin/help',component:()=>import('../setup/HelpPage.vue')},
 {path:'/about',component:()=>import('./AboutPage.vue')},
 {path:'/experiences/:kind(m|s|g|t|l|f)',component:()=>import('../life/ExperiencePage.vue')},
 {path:'/photos',component:()=>import('../life/PhotoStream.vue')},
 {path:'/trips',component:()=>import('../life/TopicIndex.vue')},
 {path:'/places',component:()=>import('../life/TopicIndex.vue')},
 {path:'/calendar',component:()=>import('../calendar/CalendarPage.vue')},
 {path:'/food',component:()=>import('../life/FoodPage.vue')},
 {path:'/drafts',component:()=>import('../writing/DraftsPage.vue')},
 {path:'/write/ai',component:()=>import('../exchange/AICreate.vue')},
 {path:'/write/:id?',component:()=>import('../writing/WritePage.vue')},
 {path:'/admin/ai',component:()=>import('../exchange/AIAdmin.vue')},
 {path:'/admin/import',component:()=>import('../exchange/ImportAdmin.vue')},
 {path:'/admin/content',component:()=>import('../admin/ContentPage.vue')},
 {path:'/admin/tags',component:()=>import('../discovery/TagAdmin.vue')},
 {path:'/admin/templates',component:()=>import('../templates/TemplateAdmin.vue')},
 {path:'/admin/trash',component:()=>import('../recovery/TrashAdmin.vue')},
 {path:'/admin/history/:id',component:()=>import('../recovery/HistoryView.vue')},
 {path:'/admin/maintenance',component:()=>import('../recovery/MaintenanceAdmin.vue')},
 {path:'/admin/appearance-lab/:id?',component:()=>import('./AppearanceLab.vue')},
 {path:'/admin/site',component:()=>import('./SiteAdmin.vue')},
 {path:'/:pathMatch(.*)*',component:()=>import('./BlogView.vue')},
]})
router.beforeEach(async(to)=>{
 const setup=await request('/setup/status').catch(()=>null)
 if(setup?.required&&to.path!=='/setup')return '/setup'
 if(to.path==='/setup'){if(setup&&!setup.required)return '/login';return}
 if(to.path==='/login')return
 if(to.hash==='#admin-content')return '/admin/content'
 try{await request('/auth/me')}catch{return {path:'/login',query:{return:to.fullPath}}}
 if(to.path==='/drafts'||to.path==='/write'||to.path.startsWith('/write/')||to.path.startsWith('/admin/')||to.path.startsWith('/preview/')){
  try{const s=await request('/admin/status');if(!s.is_admin)return '/forbidden'}catch{return '/forbidden'}
 }
})
