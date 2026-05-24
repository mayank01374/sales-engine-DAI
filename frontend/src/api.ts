import type {Opportunity, Account, ResearchTask, Campaign, SavedView, Activity, Evidence, ScoringConfig, WebDiscoveryRun, DiscoveredSignal, AppSettings, QualitySummary, LLMStatus} from './types';
const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
async function req<T>(path:string, opts:RequestInit={}): Promise<T> {
  const res = await fetch(BASE + path, {headers:{'Content-Type':'application/json', ...(opts.headers||{})}, ...opts});
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      if (typeof j.detail === 'string') {
        msg = j.detail;
      } else if (Array.isArray(j.detail) && j.detail[0]?.msg) {
        msg = j.detail[0].msg;
      } else {
        msg = j.error?.message || msg;
      }
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}
export const api = {
  opportunities: (params:Record<string, any>={}) => req<{items:Opportunity[], total:number, page:number, page_size:number}>('/api/opportunities?' + new URLSearchParams(Object.entries(params).filter(([_,v])=>v!==undefined && v!=='' && v!==null).map(([k,v])=>[k,String(v)]))),
  dailyTriggers: (params:Record<string, any>={}) => req<{items:DiscoveredSignal[], total:number, page:number, page_size:number}>('/api/daily-triggers?' + new URLSearchParams(Object.entries(params).filter(([_,v])=>v!==undefined && v!=='' && v!==null).map(([k,v])=>[k,String(v)]))),
  exportDailyTriggers: (params:Record<string, any>={})=>{ window.location.href = BASE + '/api/daily-triggers/export.csv?' + new URLSearchParams(Object.entries(params).filter(([_,v])=>v!==undefined && v!=='' && v!==null).map(([k,v])=>[k,String(v)])); },
  qualitySummary: ()=>req<QualitySummary>('/api/quality-summary'),
  settings: ()=>req<AppSettings>('/api/settings'),
  updateSettings: (payload:AppSettings)=>req<AppSettings>('/api/settings', {method:'PUT', body:JSON.stringify(payload)}),
  llmStatus: (check=false)=>req<LLMStatus>('/api/llm-status?' + new URLSearchParams({check:String(check)})),
  getOpportunity: (id:number)=>req<Opportunity>(`/api/opportunities/${id}`),
  status: (id:number,status:string)=>req<Opportunity>(`/api/opportunities/${id}/status`, {method:'PATCH', body:JSON.stringify({status})}),
  notes: (id:number,notes:string)=>req<Opportunity>(`/api/opportunities/${id}/notes`, {method:'PATCH', body:JSON.stringify({notes})}),
  enrich: (id:number)=>req<Account[]>(`/api/opportunities/${id}/enrich`, {method:'POST'}),
  enrichment: (id:number)=>req<Account[]>(`/api/opportunities/${id}/enrichment`),
  evidence: (id:number)=>req<Evidence[]>(`/api/opportunities/${id}/evidence`),
  research: (id:number)=>req<ResearchTask[]>(`/api/opportunities/${id}/research-tasks`),
  runResearch: (id:number, task_type:string)=>req<ResearchTask>(`/api/opportunities/${id}/research-tasks`, {method:'POST', body:JSON.stringify({task_type})}),
  activity: (id:number)=>req<Activity[]>(`/api/opportunities/${id}/activity`),
  campaigns: ()=>req<Campaign[]>('/api/campaigns'),
  campaign: (id:number)=>req<any>(`/api/campaigns/${id}`),
  createCampaign: (payload:any)=>req<Campaign>('/api/campaigns', {method:'POST', body:JSON.stringify(payload)}),
  addToCampaign: (cid:number, oid:number)=>req<any>(`/api/campaigns/${cid}/opportunities/${oid}`, {method:'POST'}),
  savedViews: ()=>req<SavedView[]>('/api/saved-views'),
  createView: (payload:any)=>req<SavedView>('/api/saved-views', {method:'POST', body:JSON.stringify(payload)}),
  scoring: ()=>req<ScoringConfig>('/api/scoring-config'),
  updateScoring: (payload:any)=>req<ScoringConfig>('/api/scoring-config', {method:'PUT', body:JSON.stringify(payload)}),
  rescore: ()=>req<any>('/api/opportunities/rescore', {method:'POST'}),
  findSignals: ()=>req<any>('/api/ingest/find', {method:'POST'}),
  ingestCourtListener: (query:string)=>req<any>('/api/ingest/courtlistener?' + new URLSearchParams({query, page_size:'10'}), {method:'POST'}),
  webDiscoveryRuns: ()=>req<WebDiscoveryRun[]>('/api/web-discovery/runs'),
  webDiscoveryRun: (id:number)=>req<WebDiscoveryRun>(`/api/web-discovery/runs/${id}`),
  webDiscoverySignals: (id:number, tab:string='all')=>req<DiscoveredSignal[]>(`/api/web-discovery/runs/${id}/signals?` + new URLSearchParams({tab})),
  discoveredSignal: (id:number)=>req<DiscoveredSignal>(`/api/discovered-signals/${id}`),
  createWebDiscoveryRun: (payload:any)=>req<WebDiscoveryRun>('/api/web-discovery/runs', {method:'POST', body:JSON.stringify(payload)}),
  discoveredSignalStatus: (id:number,status:string,rejection_reason='')=>req<DiscoveredSignal>(`/api/discovered-signals/${id}/status`, {method:'PATCH', body:JSON.stringify({status,rejection_reason})}),
  salesReview: (id:number,review_status:string,reason:string,notes='')=>req<DiscoveredSignal>(`/api/discovered-signals/${id}/sales-review`, {method:'PATCH', body:JSON.stringify({review_status,reason,notes})}),
  convertDiscoveredSignal: (id:number)=>req<Opportunity>(`/api/discovered-signals/${id}/convert`, {method:'POST'}),
  exportCsv: ()=>{ window.location.href = BASE + '/api/opportunities/export.csv'; },
  importCsv: async (file:File)=>{ const fd=new FormData(); fd.append('file', file); const res=await fetch(BASE+'/api/opportunities/import.csv',{method:'POST', body:fd}); if(!res.ok) throw new Error('Import failed'); return res.json(); }
};
