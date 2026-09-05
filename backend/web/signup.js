/**
 * signup.js — Public Customer Self-Signup & Pricing Page
 * Phase 2C P1: Handles the public SaaS signup journey.
 *
 * Interactions:
 *   showPricingPage()   → renders pricing cards (called from login screen CTA)
 *   showSignupForm(id)  → renders the multi-step signup form for a specific plan
 *   doSignup()          → submits POST /api/auth/customer-signup
 *   backToLogin()       → hides signup views, returns to login
 */

/* ── Utility helpers ─────────────────────────────────────────────────────── */
function _planIcon(pid){
  const icons={
    free:'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    starter:'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z',
    pro:'M13 10V3L4 14h7v7l9-11h-7z',
    enterprise:'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z'
  };
  return icons[pid]||icons.starter;
}

function _planColor(pid){
  const cols={free:'#6b7280',starter:'#6366f1',pro:'#22d3ee',enterprise:'#f59e0b'};
  return cols[pid]||'#6366f1';
}

/* ── State ───────────────────────────────────────────────────────────────── */
let _selectedPlan=null;
let _allPlans=[];

/* ── Show/hide helpers ───────────────────────────────────────────────────── */
function _hideAll(){
  ['view-login','view-pricing','view-signup'].forEach(id=>{
    const el=document.getElementById(id);
    if(el)el.style.display='none';
  });
}

function backToLogin(){
  _hideAll();
  const loginEl=document.getElementById('view-login');
  if(loginEl)loginEl.style.display='';
}

/* ── Pricing Page ────────────────────────────────────────────────────────── */
async function showPricingPage(){
  _hideAll();
  const el=document.getElementById('view-pricing');
  if(!el)return;
  el.style.display='flex';

  el.innerHTML=`<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:300px">
    <div style="width:30px;height:30px;border:2.5px solid rgba(99,102,241,.15);border-top-color:#22d3ee;border-radius:50%;animation:mvSpin 0.75s linear infinite"></div>
    <p style="color:#9ca3af;font-size:13px;margin-top:12px">Loading plans…</p>
  </div>`;

  try{
    const plans=await fetch('/api/plans').then(r=>r.json());
    _allPlans=plans;
    _renderPricingCards(plans);
  }catch(e){
    el.innerHTML=`<p style="color:#f87171;padding:48px;text-align:center">${e.message}</p>`;
  }
}

function _renderPricingCards(plans){
  const el=document.getElementById('view-pricing');
  if(!el)return;
  el.innerHTML=`
  <div style="width:100%;max-width:1100px;padding:40px 24px 60px">
    <!-- Back / Brand -->
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:48px">
      <button onclick="backToLogin()" style="background:none;border:none;cursor:pointer;color:#9ca3af;display:flex;align-items:center;gap:6px;font-size:13px;font-weight:500;padding:0">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M19 12H5M12 19l-7-7 7-7"/></svg>
        Back to Sign In
      </button>
      <img src="/api/web/logo-dark.png?v=20260603" style="height:28px;margin-left:auto" alt="MediAd View">
    </div>

    <!-- Heading -->
    <div style="text-align:center;margin-bottom:48px">
      <h1 style="font-size:38px;font-weight:800;color:#f3f4f6;line-height:1.15;margin-bottom:12px">Simple, transparent pricing</h1>
      <p style="font-size:16px;color:#9ca3af;max-width:520px;margin:0 auto">Start for free. Scale as you grow. All plans include a 14-day trial (except Free).</p>
    </div>

    <!-- Plan cards -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:20px">
      ${plans.map(p=>`
        <div style="background:#111827;border:2px solid ${p.highlight?_planColor(p.plan_id):'#1f2937'};border-radius:16px;padding:28px;display:flex;flex-direction:column;gap:18px;position:relative;transition:border-color .2s">
          ${p.highlight?`<div style="position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:${_planColor(p.plan_id)};color:#fff;font-size:11px;font-weight:700;padding:4px 14px;border-radius:20px;letter-spacing:.05em;white-space:nowrap">${p.highlight_text||'Popular'}</div>`:''}
          <div>
            <div style="width:44px;height:44px;border-radius:12px;background:${_planColor(p.plan_id)}22;border:1px solid ${_planColor(p.plan_id)}44;display:flex;align-items:center;justify-content:center;margin-bottom:14px">
              <svg width="20" height="20" fill="none" stroke="${_planColor(p.plan_id)}" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${_planIcon(p.plan_id)}"/></svg>
            </div>
            <div style="font-size:18px;font-weight:700;color:#f3f4f6;margin-bottom:6px">${p.display_name}</div>
            <div style="display:flex;align-items:baseline;gap:4px">
              <span style="font-size:32px;font-weight:800;color:#f3f4f6">${p.monthly_price===0?'Free':'$'+p.monthly_price}</span>
              ${p.monthly_price>0?'<span style="font-size:13px;color:#9ca3af">/month</span>':''}
            </div>
            ${p.trial_days>0?`<div style="font-size:11px;color:#34d399;font-weight:600;margin-top:4px">${p.trial_days}-day free trial</div>`:''}
          </div>
          <ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:8px">
            ${(p.features||[]).map(f=>`<li style="display:flex;align-items:flex-start;gap:8px;font-size:13px;color:#d1d5db">
              <svg width="16" height="16" fill="none" stroke="#34d399" stroke-width="2.5" viewBox="0 0 24 24" style="flex-shrink:0;margin-top:1px"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>
              ${f}
            </li>`).join('')}
          </ul>
          <button onclick="showSignupForm('${p.plan_id}')" style="margin-top:auto;width:100%;padding:12px;border-radius:10px;border:2px solid ${p.highlight?_planColor(p.plan_id):'#374151'};background:${p.highlight?_planColor(p.plan_id):'transparent'};color:#f3f4f6;font-size:14px;font-weight:600;cursor:pointer;transition:all .2s">
            ${p.plan_id==='free'?'Start Free':'Get Started'}
          </button>
        </div>
      `).join('')}
    </div>

    <!-- Enterprise CTA -->
    <div style="text-align:center;margin-top:40px;padding:28px;background:#111827;border:1px solid #1f2937;border-radius:16px">
      <p style="font-size:15px;color:#9ca3af;margin-bottom:8px">Need a custom solution? We handle custom contracts for enterprise customers.</p>
      <p style="font-size:13px;color:#6b7280">Contact us at <a href="mailto:sales@mediadview.com" style="color:#6366f1">sales@mediadview.com</a></p>
    </div>
  </div>`;
}

/* ── Signup Form ─────────────────────────────────────────────────────────── */
async function showSignupForm(planId){
  _selectedPlan=planId||'starter';

  // Find plan config
  let plan=_allPlans.find(p=>p.plan_id===_selectedPlan);
  if(!plan&&_allPlans.length===0){
    try{_allPlans=await fetch('/api/plans').then(r=>r.json());}catch(_){}
    plan=_allPlans.find(p=>p.plan_id===_selectedPlan);
  }

  _hideAll();
  const el=document.getElementById('view-signup');
  if(!el)return;
  el.style.display='flex';

  el.innerHTML=`
  <div style="width:100%;max-width:520px;padding:40px 24px 60px">
    <!-- Back -->
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:36px">
      <button onclick="showPricingPage()" style="background:none;border:none;cursor:pointer;color:#9ca3af;display:flex;align-items:center;gap:6px;font-size:13px;font-weight:500;padding:0">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M19 12H5M12 19l-7-7 7-7"/></svg>
        Change Plan
      </button>
      <img src="/api/web/logo-dark.png?v=20260603" style="height:26px;margin-left:auto" alt="MediAd View">
    </div>

    <!-- Plan summary badge -->
    ${plan?`<div style="display:flex;align-items:center;gap:12px;background:#111827;border:1px solid ${_planColor(plan.plan_id)}44;border-radius:12px;padding:16px 20px;margin-bottom:28px">
      <div style="width:36px;height:36px;border-radius:10px;background:${_planColor(plan.plan_id)}22;display:flex;align-items:center;justify-content:center;flex-shrink:0">
        <svg width="18" height="18" fill="none" stroke="${_planColor(plan.plan_id)}" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${_planIcon(plan.plan_id)}"/></svg>
      </div>
      <div>
        <div style="font-size:14px;font-weight:700;color:#f3f4f6">${plan.display_name} Plan ${plan.trial_days>0?'· '+plan.trial_days+'-day free trial':''}</div>
        <div style="font-size:12px;color:#9ca3af">${plan.monthly_price===0?'Free forever':'$'+plan.monthly_price+'/month after trial'}</div>
      </div>
    </div>`:''}

    <h2 style="font-size:24px;font-weight:800;color:#f3f4f6;margin-bottom:6px">Create your account</h2>
    <p style="font-size:13px;color:#9ca3af;margin-bottom:28px">Fill in your details to get started. No credit card required.</p>

    <div style="display:flex;flex-direction:column;gap:16px">
      <div>
        <label style="font-size:12px;font-weight:600;color:#9ca3af;display:block;margin-bottom:6px;letter-spacing:.04em;text-transform:uppercase">Business / Company Name *</label>
        <input id="su-business" type="text" placeholder="Acme Corp" style="width:100%;padding:11px 14px;background:#111827;border:1px solid #374151;border-radius:8px;color:#f3f4f6;font-size:14px;outline:none;box-sizing:border-box" onfocus="this.style.borderColor='#6366f1'" onblur="this.style.borderColor='#374151'">
      </div>
      <div>
        <label style="font-size:12px;font-weight:600;color:#9ca3af;display:block;margin-bottom:6px;letter-spacing:.04em;text-transform:uppercase">Your Full Name *</label>
        <input id="su-name" type="text" placeholder="Jane Smith" style="width:100%;padding:11px 14px;background:#111827;border:1px solid #374151;border-radius:8px;color:#f3f4f6;font-size:14px;outline:none;box-sizing:border-box" onfocus="this.style.borderColor='#6366f1'" onblur="this.style.borderColor='#374151'">
      </div>
      <div>
        <label style="font-size:12px;font-weight:600;color:#9ca3af;display:block;margin-bottom:6px;letter-spacing:.04em;text-transform:uppercase">Work Email *</label>
        <input id="su-email" type="email" placeholder="jane@acme.com" style="width:100%;padding:11px 14px;background:#111827;border:1px solid #374151;border-radius:8px;color:#f3f4f6;font-size:14px;outline:none;box-sizing:border-box" onfocus="this.style.borderColor='#6366f1'" onblur="this.style.borderColor='#374151'">
      </div>
      <div>
        <label style="font-size:12px;font-weight:600;color:#9ca3af;display:block;margin-bottom:6px;letter-spacing:.04em;text-transform:uppercase">Phone (optional)</label>
        <input id="su-phone" type="tel" placeholder="+1 555 000 0000" style="width:100%;padding:11px 14px;background:#111827;border:1px solid #374151;border-radius:8px;color:#f3f4f6;font-size:14px;outline:none;box-sizing:border-box" onfocus="this.style.borderColor='#6366f1'" onblur="this.style.borderColor='#374151'">
      </div>
      <div>
        <label style="font-size:12px;font-weight:600;color:#9ca3af;display:block;margin-bottom:6px;letter-spacing:.04em;text-transform:uppercase">Password *</label>
        <input id="su-pwd" type="password" placeholder="At least 8 characters" style="width:100%;padding:11px 14px;background:#111827;border:1px solid #374151;border-radius:8px;color:#f3f4f6;font-size:14px;outline:none;box-sizing:border-box" onfocus="this.style.borderColor='#6366f1'" onblur="this.style.borderColor='#374151'" onkeydown="if(event.key==='Enter')doSignup()">
      </div>
    </div>

    <div id="su-err" style="display:none;background:#7f1d1d;border:1px solid #dc2626;border-radius:8px;padding:10px 14px;margin-top:16px;font-size:13px;color:#fca5a5"></div>

    <button id="su-btn" onclick="doSignup()" style="width:100%;padding:14px;background:#6366f1;border:none;border-radius:10px;color:#fff;font-size:15px;font-weight:700;cursor:pointer;margin-top:20px;transition:opacity .2s">
      Create Account & Start Trial
    </button>
    <p style="font-size:11px;color:#6b7280;text-align:center;margin-top:14px">
      By creating an account you agree to our 
      <a href="/api/landing" style="color:#9ca3af">Terms of Service</a> and 
      <a href="/api/landing" style="color:#9ca3af">Privacy Policy</a>.
    </p>
    <p style="text-align:center;margin-top:16px;font-size:13px;color:#9ca3af">
      Already have an account? 
      <a onclick="backToLogin()" style="color:#6366f1;cursor:pointer;font-weight:600">Sign In</a>
    </p>
  </div>`;
}

async function doSignup(){
  const business=document.getElementById('su-business')?.value.trim();
  const name=document.getElementById('su-name')?.value.trim();
  const email=document.getElementById('su-email')?.value.trim();
  const phone=document.getElementById('su-phone')?.value.trim();
  const pwd=document.getElementById('su-pwd')?.value;
  const errEl=document.getElementById('su-err');
  const btn=document.getElementById('su-btn');
  if(!errEl||!btn)return;

  // Client-side validation
  if(!business){_suErr('Please enter your business name.');return;}
  if(!name){_suErr('Please enter your full name.');return;}
  if(!email||!email.includes('@')){_suErr('Please enter a valid email address.');return;}
  if(!pwd||pwd.length<8){_suErr('Password must be at least 8 characters.');return;}

  btn.disabled=true;
  btn.textContent='Creating account…';
  errEl.style.display='none';

  try{
    const res=await fetch('/api/auth/customer-signup',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        plan_id:_selectedPlan||'starter',
        business_name:business,
        contact_name:name,
        contact_email:email,
        contact_phone:phone||null,
        password:pwd
      })
    });
    const data=await res.json();
    if(!res.ok){
      _suErr(data.detail||'Signup failed. Please try again.');
      btn.disabled=false;
      btn.textContent='Create Account & Start Trial';
      return;
    }

    // Success — log in with fresh credentials
    btn.textContent='Signing in…';
    try{
      const u=await window.Auth.login(email,pwd);
      window.user=u;
      // Trigger enterApp
      if(typeof enterApp==='function'){
        _hideAll();
        enterApp();
      }
    }catch(loginErr){
      // Fallback: show success and direct to login
      _suErr('Account created! Please sign in with your email and password.');
      setTimeout(()=>backToLogin(),2000);
    }
  }catch(e){
    _suErr(e.message||'Network error. Please try again.');
    btn.disabled=false;
    btn.textContent='Create Account & Start Trial';
  }
}

function _suErr(msg){
  const el=document.getElementById('su-err');
  if(el){el.textContent=msg;el.style.display='block';}
}

// Expose globally
window.showPricingPage=showPricingPage;
window.showSignupForm=showSignupForm;
window.doSignup=doSignup;
window.backToLogin=backToLogin;
