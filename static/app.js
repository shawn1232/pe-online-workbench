
let APP_STATE = {
  report: null,
  scoringGuide: [],
  modules: [],
  activeJob: null,
  selectedCompany: null,
  admin: { loggedIn: false, lastJobId: null, showWeights: false }
};

function qs(id) { return document.getElementById(id); }
function fmt(v){ return v == null ? '--' : v; }
function escapeHtml(str){ return (str || '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }

async function api(url, options={}){
  const res = await fetch(url, {
    headers: {'Content-Type':'application/json'},
    credentials: 'same-origin',
    ...options
  });
  const data = await res.json().catch(()=>({ok:false,error:'接口返回异常'}));
  if(!res.ok) throw new Error(data.error || '请求失败');
  return data;
}

async function loadPublicState(){
  const data = await api('/api/public/state');
  APP_STATE.report = data.report;
  APP_STATE.scoringGuide = data.scoring_guide || [];
  APP_STATE.modules = data.modules || [];
  APP_STATE.activeJob = data.active_job || null;
  renderAll(data);
}

function renderAll(payload){
  const report = payload.report;
  qs('headline').textContent = report.meta.headline || '一级PE在线项目工作台';
  qs('systemPositioningText').textContent = payload.system_positioning || '';
  qs('methodSummary').textContent = report.meta.method_summary || '';
  qs('sourceBadge').textContent = payload.source === 'live' ? '最近一次为实时更新' : (payload.source === 'seed' ? '当前为内置样例' : '当前为缓存结果');
  qs('sourceBadge').className = 'badge ' + (payload.source === 'live' ? 'success' : 'ghost');
  qs('topSectorValue').textContent = report.top_sectors?.[0]?.sector || '--';
  qs('topSectorNote').textContent = report.top_sectors?.[0]?.why_now || '等待更新';
  qs('topCompanyValue').textContent = report.final_recommendation?.recommended_company || '--';
  qs('topCompanyNote').textContent = report.final_recommendation?.recommendation_logic || '等待更新';
  qs('candidateCountValue').textContent = (report.candidate_companies || []).length;
  qs('candidateCountNote').textContent = report.meta.search_scope || '--';
  qs('savedAtValue').textContent = payload.saved_at || '--';
  qs('savedAtNote').textContent = payload.public_note || '公开页默认展示最近一次成功结果';
  renderModules();
  renderTopSectors();
  renderFinalRecommendation();
  renderCompanyTable();
  renderComparison();
  renderScoringGuide();
  renderSources();
  if((report.candidate_companies || []).length && !APP_STATE.selectedCompany){
    APP_STATE.selectedCompany = report.candidate_companies[0];
  }
  renderCompanyDetail(APP_STATE.selectedCompany);
  if(payload.active_job){
    renderJobStatus(payload.active_job);
  }
}

function renderModules(){
  qs('moduleGrid').innerHTML = APP_STATE.modules.map(m => `
    <div class="module-card">
      <h3>${escapeHtml(m.title)}</h3>
      <p>${escapeHtml(m.desc)}</p>
    </div>
  `).join('');
}

function renderTopSectors(){
  const sectors = APP_STATE.report.top_sectors || [];
  qs('sectorCards').innerHTML = sectors.slice(0,4).map((s, i) => `
    <div class="sector-card ${i===0?'highlight':''}">
      <div class="sector-name">${escapeHtml(s.sector)}</div>
      <div class="sector-mainline">${escapeHtml(s.investment_mainline)}</div>
      <div class="sector-tag">${escapeHtml(s.signal_type)}</div>
      <div class="sector-why">${escapeHtml(s.why_now)}</div>
    </div>
  `).join('') || '<div class="empty-state">还没有赛道输出，请先更新。</div>';
  qs('pptSummary').textContent = APP_STATE.report.final_recommendation?.summary_for_ppt || '--';
}

function renderFinalRecommendation(){
  const fin = APP_STATE.report.final_recommendation || {};
  const backups = (fin.backup_companies || []).map(x => `<span class="pill">${escapeHtml(x)}</span>`).join(' ');
  const excludes = (fin.excluded_companies || []).map(x => `<span class="pill ghost">${escapeHtml(x)}</span>`).join(' ');
  qs('finalRecommendationBox').innerHTML = `
    <div class="final-box">
      <div class="final-main">当前最终推荐：<strong>${escapeHtml(fin.recommended_company || '--')}</strong></div>
      <div class="final-logic">${escapeHtml(fin.recommendation_logic || '等待生成')}</div>
      <div class="subsection-title">备选公司</div>
      <div>${backups || '<span class="empty-inline">暂无</span>'}</div>
      <div class="subsection-title">当前排除</div>
      <div>${excludes || '<span class="empty-inline">暂无</span>'}</div>
    </div>
  `;
}

function companyMatches(c, q){
  if(!q) return true;
  const s = [c.name, c.sector, c.stage, c.value_node, c.tracking_stage, c.main_recommendation_reason].join(' ').toLowerCase();
  return s.includes(q.toLowerCase());
}

function renderCompanyTable(){
  const q = qs('companySearch').value.trim();
  const rows = (APP_STATE.report.candidate_companies || []).filter(c => companyMatches(c, q));
  qs('companyTbody').innerHTML = rows.map(c => `
    <tr data-company="${encodeURIComponent(c.name)}" class="${APP_STATE.selectedCompany?.name===c.name?'active':''}">
      <td><div class="company-name">${escapeHtml(c.name)}</div><div class="mini-note">${escapeHtml(c.value_node || '')}</div></td>
      <td>${escapeHtml(c.sector || '--')}</td>
      <td>${escapeHtml(c.stage || '--')}</td>
      <td><span class="score-pill">${fmt(c._computed?.total_score)}</span></td>
      <td>${escapeHtml(c.tracking_stage || '--')}</td>
      <td>${escapeHtml((c.main_recommendation_reason || '').slice(0,48))}${(c.main_recommendation_reason || '').length > 48 ? '…' : ''}</td>
    </tr>
  `).join('') || '<tr><td colspan="6" class="empty-cell">没有匹配公司</td></tr>';
  [...qs('companyTbody').querySelectorAll('tr[data-company]')].forEach(tr => {
    tr.addEventListener('click', () => {
      const name = decodeURIComponent(tr.getAttribute('data-company'));
      APP_STATE.selectedCompany = (APP_STATE.report.candidate_companies || []).find(x => x.name === name);
      renderCompanyTable();
      renderCompanyDetail(APP_STATE.selectedCompany);
    });
  });
}

function renderCompanyDetail(c){
  if(!c){
    qs('detailEmpty').classList.remove('hidden');
    qs('detailContent').classList.add('hidden');
    qs('detailTag').textContent = '未选择';
    return;
  }
  qs('detailEmpty').classList.add('hidden');
  qs('detailContent').classList.remove('hidden');
  qs('detailTag').textContent = c._computed?.score_bucket || '--';
  qs('detailTag').className = 'badge ' + ((c._computed?.score_bucket || '').includes('最终') ? 'success' : 'ghost');
  qs('detailName').textContent = c.name;
  qs('detailSubtitle').textContent = `${c.sector || '--'} ｜ ${c.stage || '--'} ｜ ${c.listed_status || '--'} ｜ ${c.tracking_stage || '--'}`;
  qs('detailScore').textContent = fmt(c._computed?.total_score);
  qs('detailThesis').textContent = c.investment_thesis || '--';
  qs('detailWhySelected').textContent = c.why_selected_over_peers || c.main_recommendation_reason || '--';
  qs('detailWhyNotOthers').textContent = c.why_not_others || '--';
  qs('detailExclusion').textContent = c.exclusion_logic || '--';
  qs('detailNextAction').textContent = c.next_action || '--';

  const scoreBars = APP_STATE.scoringGuide.map(item => {
    const raw = c.score_levels?.[item.key] || 0;
    const weighted = c._computed?.dimension_scores?.[item.key] || 0;
    return `
      <div class="score-row">
        <div class="score-row-head">
          <span>${escapeHtml(item.label)}</span>
          <span>${raw}/5</span>
        </div>
        <div class="bar"><div class="bar-fill" style="width:${(raw/5)*100}%"></div></div>
        <div class="score-row-foot">判断口径：${escapeHtml(item.guide)} ｜ 加权得分：${weighted}</div>
      </div>
    `;
  }).join('');
  qs('scoreBars').innerHTML = scoreBars;
  qs('detailGaps').innerHTML = (c.info_gaps || []).map(x => `<li>${escapeHtml(x)}</li>`).join('') || '<li>暂无</li>';
  qs('detailSwitch').innerHTML = (c.switch_variables || []).map(x => `<li>${escapeHtml(x)}</li>`).join('') || '<li>暂无</li>';
  qs('detailEvidence').innerHTML = (c.evidence || []).map(e => `
    <a class="evidence-card" href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener noreferrer">
      <div class="evidence-head">
        <span class="pill small">${escapeHtml(e.event_type)}</span>
        <span class="mini-note">${escapeHtml(e.date)}</span>
      </div>
      <div class="evidence-title">${escapeHtml(e.title)}</div>
      <div class="evidence-summary">${escapeHtml(e.summary)}</div>
      <div class="evidence-domain">${escapeHtml(e.source_domain)}</div>
    </a>
  `).join('') || '<div class="empty-state">暂无公开证据</div>';
}

function renderComparison(){
  const groups = {};
  (APP_STATE.report.candidate_companies || []).forEach(c => {
    (groups[c.sector] ||= []).push(c);
  });
  const html = Object.entries(groups).map(([sector, arr]) => {
    arr.sort((a,b)=>(b._computed?.total_score||0) - (a._computed?.total_score||0));
    const winner = arr[0];
    const others = arr.slice(1,4).map(x => `<li><strong>${escapeHtml(x.name)}</strong>：${escapeHtml(x.why_not_others || x.exclusion_logic || '待补充')}</li>`).join('');
    return `
      <div class="comparison-card">
        <div class="comparison-sector">${escapeHtml(sector)}</div>
        <div class="comparison-winner">优先公司：<strong>${escapeHtml(winner?.name || '--')}</strong>（${fmt(winner?._computed?.total_score)}）</div>
        <div class="comparison-why">${escapeHtml(winner?.why_selected_over_peers || winner?.main_recommendation_reason || '--')}</div>
        <div class="subsection-title">其余候选未优先原因</div>
        <ul>${others || '<li>暂无</li>'}</ul>
      </div>
    `;
  }).join('');
  qs('comparisonCards').innerHTML = html || '<div class="empty-state">暂无横向比较结果</div>';
}

function renderScoringGuide(){
  qs('scoreGuideTable').innerHTML = `
    <div class="guide-table">
      ${APP_STATE.scoringGuide.map(item => `
        <div class="guide-row">
          <div class="guide-name">${escapeHtml(item.label)}</div>
          <div class="guide-band">权重带：${escapeHtml(item.band)}</div>
          <div class="guide-desc">${escapeHtml(item.guide)}</div>
        </div>
      `).join('')}
    </div>
  `;
  qs('internalWeightBox').innerHTML = APP_STATE.scoringGuide.map(item => `
    <div class="weight-row"><span>${escapeHtml(item.label)}</span><strong>${item.weight}</strong></div>
  `).join('') + '<div class="weight-row total-row"><span>排除项惩罚</span><strong>最高 -20</strong></div>';
}

function renderSources(){
  const sources = APP_STATE.report.sources || [];
  qs('sourceSummary').innerHTML = `当前缓存覆盖 <strong>${sources.length}</strong> 条公开来源；公开页默认展示最近一次成功结果，以避免现场实时刷新失败导致演示中断。`;
  qs('sourceList').innerHTML = sources.slice(0,30).map(s => `
    <a class="source-item" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">
      <div class="source-title">${escapeHtml(s.title)}</div>
      <div class="source-domain">${escapeHtml(s.domain)}</div>
    </a>
  `).join('') || '<div class="empty-state">暂无来源列表</div>';
}

function openModal(id){ qs(id).classList.remove('hidden'); }
function closeModal(id){ qs(id).classList.add('hidden'); }

async function doLogin(){
  const password = qs('loginPassword').value;
  try {
    await api('/api/admin/login', {method:'POST', body: JSON.stringify({password})});
    APP_STATE.admin.loggedIn = true;
    qs('loginMsg').textContent = '登录成功';
    closeModal('loginModal');
    qs('openAdminBtn').classList.remove('hidden');
    qs('openLoginBtn').classList.add('hidden');
    await loadAdminStatus();
    openModal('adminDrawer');
  } catch(err){
    qs('loginMsg').textContent = err.message;
  }
}

async function loadAdminStatus(){
  try {
    const data = await api('/api/admin/status');
    const s = data.settings || {};
    qs('settingScope').value = s.scope || '';
    qs('settingBrief').value = s.brief || '';
    qs('settingStagePref').value = s.stage_pref || '';
    qs('settingGeography').value = s.geography || '';
    qs('settingMaxCompanies').value = s.max_companies || 8;
    qs('settingModel').value = s.model || '';
    qs('settingAllowedDomains').value = s.allowed_domains || '';
    qs('settingBaseUrl').value = s.openai_base_url || '';
    qs('settingExcludeDirections').value = s.exclude_directions || '';
    qs('settingExcludeCompanies').value = s.exclude_companies || '';
    qs('settingAdminNote').value = s.admin_note || '';
    qs('keySourceText').textContent = data.api_key_source || '--';
    qs('keyMaskText').textContent = data.api_key_mask || '--';
    qs('historyList').innerHTML = (data.history || []).map(x => `<div class="history-item"><strong>${escapeHtml(x.recommended_company || '--')}</strong><span>${escapeHtml(x.saved_at || '')}</span></div>`).join('') || '<div class="empty-state">暂无历史</div>';
  } catch(err){
    qs('adminMsg').textContent = err.message;
  }
}

async function saveSettings(){
  const payload = {
    scope: qs('settingScope').value,
    brief: qs('settingBrief').value,
    stage_pref: qs('settingStagePref').value,
    geography: qs('settingGeography').value,
    max_companies: Number(qs('settingMaxCompanies').value || 8),
    model: qs('settingModel').value,
    allowed_domains: qs('settingAllowedDomains').value,
    openai_base_url: qs('settingBaseUrl').value,
    exclude_directions: qs('settingExcludeDirections').value,
    exclude_companies: qs('settingExcludeCompanies').value,
    admin_note: qs('settingAdminNote').value,
    api_key: qs('settingApiKey').value
  };
  try {
    const data = await api('/api/admin/settings', {method:'POST', body: JSON.stringify(payload)});
    qs('adminMsg').textContent = '设置已保存';
    qs('settingApiKey').value = '';
    qs('keySourceText').textContent = data.api_key_source || '--';
    qs('keyMaskText').textContent = data.api_key_mask || '--';
    await loadPublicState();
  } catch(err){
    qs('adminMsg').textContent = err.message;
  }
}

function renderJobStatus(job){
  if(!job) return;
  qs('jobStatusBadge').textContent = job.status || '--';
  qs('jobStatusBadge').className = 'badge ' + (job.status === 'completed' ? 'success' : (job.status === 'failed' ? 'danger' : 'ghost'));
  qs('jobLog').textContent = (job.logs || []).join('\n');
}

async function startRefresh(){
  qs('adminMsg').textContent = '';
  try {
    await saveSettings();
    const data = await api('/api/admin/refresh', {method:'POST', body: JSON.stringify({})});
    APP_STATE.admin.lastJobId = data.job_id;
    qs('adminMsg').textContent = '已触发更新';
    pollJob();
  } catch(err){
    qs('adminMsg').textContent = err.message;
  }
}

async function pollJob(){
  if(!APP_STATE.admin.lastJobId) return;
  try {
    const data = await api(`/api/admin/job/${APP_STATE.admin.lastJobId}`);
    const job = data.job;
    renderJobStatus(job);
    if(job.status === 'completed'){
      await loadPublicState();
      await loadAdminStatus();
      return;
    }
    if(job.status === 'failed'){
      return;
    }
    setTimeout(pollJob, 2500);
  } catch(err){
    qs('adminMsg').textContent = err.message;
  }
}

async function resetSeed(){
  try {
    await api('/api/admin/reset-to-seed', {method:'POST', body: JSON.stringify({})});
    await loadPublicState();
    await loadAdminStatus();
    qs('adminMsg').textContent = '已恢复为内置样例';
  } catch(err){
    qs('adminMsg').textContent = err.message;
  }
}

async function logout(){
  await api('/api/admin/logout', {method:'POST', body: JSON.stringify({})});
  APP_STATE.admin.loggedIn = false;
  qs('openAdminBtn').classList.add('hidden');
  qs('openLoginBtn').classList.remove('hidden');
  closeModal('adminDrawer');
}

function bindEvents(){
  qs('openLoginBtn').addEventListener('click', ()=>openModal('loginModal'));
  qs('openAdminBtn').addEventListener('click', async ()=>{ await loadAdminStatus(); openModal('adminDrawer'); });
  qs('loginBtn').addEventListener('click', doLogin);
  qs('companySearch').addEventListener('input', renderCompanyTable);
  qs('saveSettingsBtn').addEventListener('click', saveSettings);
  qs('refreshBtn').addEventListener('click', startRefresh);
  qs('seedBtn').addEventListener('click', resetSeed);
  qs('logoutBtn').addEventListener('click', logout);
  qs('showWeightsBtn').addEventListener('click', ()=>{
    APP_STATE.admin.showWeights = !APP_STATE.admin.showWeights;
    qs('internalWeightBox').classList.toggle('hidden', !APP_STATE.admin.showWeights);
    qs('showWeightsBtn').textContent = APP_STATE.admin.showWeights ? '隐藏内部权重' : '显示内部权重';
  });
  document.querySelectorAll('[data-close]').forEach(el=>el.addEventListener('click', ()=>closeModal(el.getAttribute('data-close'))));
}

document.addEventListener('DOMContentLoaded', async () => {
  bindEvents();
  await loadPublicState();
});
