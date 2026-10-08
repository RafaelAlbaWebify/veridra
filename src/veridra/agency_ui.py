from __future__ import annotations

import html

AGENCY_DESIGN_SYSTEM = """
<style>
:root{
  --veridra-canvas:#0b0e12;
  --veridra-panel:#0d151d;
  --veridra-panel-strong:#0c1d2a;
  --veridra-panel-soft:#101820;
  --veridra-text:#e8edf2;
  --veridra-text-secondary:#9aa4b1;
  --veridra-label:#8b96a5;
  --veridra-border:#242a32;
  --veridra-border-secondary:#2a313b;
  --veridra-success:#7fb48a;
  --veridra-warning:#d6b777;
  --veridra-danger:#d39a8f;
  --veridra-accent:#67b7ff;
  --veridra-gap:14px;
  --veridra-radius:13px;
}
*{box-sizing:border-box}
html{background:var(--veridra-canvas)}
body{
  margin:0!important;
  min-width:320px;
  min-height:100vh;
  background:
    radial-gradient(circle at 15% 8%,rgba(69,89,112,.13),transparent 28%),
    var(--veridra-canvas)!important;
  color:var(--veridra-text)!important;
  font:13px Inter,ui-sans-serif,system-ui,-apple-system,
    BlinkMacSystemFont,"Segoe UI",sans-serif!important;
  text-rendering:optimizeLegibility;
}
body>main{
  max-width:none!important;
  margin:0!important;
  padding:76px 22px 24px!important;
}
a{color:#a9d2f5}
a:hover{color:#d8edff}
h1,h2,h3{color:var(--veridra-text);letter-spacing:-.02em}
h1{font-size:clamp(25px,2.3vw,34px);line-height:1.06}
h2{font-size:18px;line-height:1.15}
p{line-height:1.5}
.muted{color:var(--veridra-text-secondary)!important}
.eyebrow,.label{
  color:var(--veridra-label)!important;
  font-size:10px!important;
  font-weight:700;
  letter-spacing:.12em!important;
  text-transform:uppercase;
}
.agency-nav{
  position:fixed!important;
  inset:0 0 auto 0!important;
  width:100%!important;
  min-height:58px;
  z-index:50;
  display:grid!important;
  grid-template-columns:auto minmax(0,1fr) auto;
  align-items:center;
  gap:18px!important;
  margin:0!important;
  padding:8px 18px!important;
  overflow:visible!important;
  background:rgba(7,13,19,.96)!important;
  border:0!important;
  border-bottom:1px solid var(--veridra-border)!important;
  backdrop-filter:blur(14px);
}
.agency-nav .nav-brand{
  display:flex!important;
  align-items:baseline;
  gap:9px;
  margin:0!important;
  color:#f4f8fb!important;
  font-size:20px!important;
  font-weight:760!important;
  letter-spacing:-.03em!important;
  white-space:nowrap;
}
.agency-nav .nav-brand small{
  display:inline!important;
  margin:0!important;
  color:#6f8494!important;
  font-size:9px!important;
  font-weight:700!important;
  text-transform:uppercase;
  letter-spacing:.10em!important;
}
.agency-nav .nav-links{
  display:flex;
  align-items:center;
  gap:4px;
  min-width:0;
  overflow-x:auto;
  scrollbar-width:none;
}
.agency-nav .nav-links::-webkit-scrollbar{display:none}
.agency-nav .nav-group{display:none!important}
.agency-nav a{
  display:inline-flex!important;
  width:auto!important;
  min-height:32px;
  align-items:center;
  justify-content:center;
  border:1px solid transparent!important;
  border-radius:8px!important;
  background:transparent!important;
  color:#96a6b3!important;
  padding:7px 10px!important;
  font-size:11px!important;
  font-weight:600;
  text-decoration:none!important;
  white-space:nowrap;
}
.agency-nav a:hover{
  background:#101c25!important;
  border-color:#213342!important;
  color:#eef5fa!important;
}
.agency-nav a[aria-current='page']{
  background:#102332!important;
  border-color:#2b4a60!important;
  color:#eef5fa!important;
}
.nav-context{
  display:flex;
  align-items:center;
  gap:7px;
  white-space:nowrap;
}
.status-chip{
  display:inline-flex;
  align-items:center;
  gap:6px;
  border:1px solid var(--veridra-border-secondary);
  border-radius:999px;
  background:#0d151d;
  color:#899aa7;
  padding:5px 8px;
  font-size:9px;
  font-weight:700;
  letter-spacing:.05em;
  text-transform:uppercase;
}
.status-chip::before{
  content:"";
  width:6px;
  height:6px;
  border-radius:999px;
  background:#677583;
}
.status-chip.ok::before{background:var(--veridra-success)}
.status-chip.guard::before{background:var(--veridra-warning)}
.agency-workbench{
  width:min(1500px,100%);
  margin:0 auto;
}
.agency-workbench>section,
.workbench-pane,
section,
.card,
.links a,
.step{
  background:linear-gradient(180deg,rgba(12,29,42,.90),rgba(8,21,31,.93))!important;
  border:1px solid var(--veridra-border)!important;
  border-radius:var(--veridra-radius)!important;
  color:var(--veridra-text)!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.015)!important;
}
.workbench-head{
  padding:16px 18px!important;
  margin-bottom:var(--veridra-gap)!important;
}
.workbench-head h1{margin:2px 0 6px}
.workbench-body{padding:0!important;background:transparent!important;border:0!important}
.workbench-scroll,.workbench-cards{padding:0!important}
.workbench-scroll thead th{position:sticky;top:0;z-index:2}
.agency-workbench input,
.agency-workbench textarea,
.agency-workbench select{
  box-sizing:border-box;
  max-width:100%;
}
.workbench-pane{padding:16px!important}
.button,button{
  display:inline-flex!important;
  align-items:center;
  justify-content:center;
  min-height:34px;
  border:1px solid #35556d!important;
  border-radius:8px!important;
  background:#102b3e!important;
  color:#edf7ff!important;
  padding:8px 12px!important;
  font:inherit!important;
  font-size:11px!important;
  font-weight:700!important;
  text-decoration:none!important;
  cursor:pointer;
}
.button:hover,button:hover{background:#153951!important;border-color:#4a7898!important}
.button.secondary,.secondary{
  background:#111a22!important;
  border-color:var(--veridra-border-secondary)!important;
  color:#aab7c2!important;
}
.actions{display:flex;gap:8px;flex-wrap:wrap}
input,select,textarea{
  width:100%;
  border:1px solid var(--veridra-border-secondary)!important;
  border-radius:8px!important;
  background:#0d141b!important;
  color:var(--veridra-text)!important;
  padding:9px 10px!important;
  font:inherit!important;
}
input::placeholder,textarea::placeholder{color:#5f6c78}
input:focus,select:focus,textarea:focus{
  outline:1px solid #4f7089;
  outline-offset:1px;
  border-color:#4f7089!important;
}
label{color:#c8d1d9}
table{
  width:100%;
  border-collapse:collapse;
  background:rgba(255,255,255,.01)!important;
  color:var(--veridra-text)!important;
}
th{
  color:#7f93a2!important;
  background:#0c151d!important;
  font-size:9px!important;
  letter-spacing:.08em;
  text-transform:uppercase;
}
th,td{border-color:#1d2933!important;padding:9px 10px!important}
tr:hover td{background:rgba(103,183,255,.025)}
.notice{
  border:1px solid #2b3a46!important;
  border-left:3px solid #657b8d!important;
  border-radius:9px!important;
  background:#0d1821!important;
  color:#aab7c2!important;
  padding:10px 12px!important;
}
.notice.success{border-left-color:var(--veridra-success)!important}
.help-tip{
  position:relative;
  display:inline-grid;
  place-items:center;
  width:17px;
  height:17px;
  margin-left:5px;
  border:1px solid #344554;
  border-radius:999px;
  color:#8495a3;
  font-size:10px;
  font-weight:800;
  cursor:help;
  vertical-align:middle;
}
.help-tip::after{
  content:attr(data-help);
  position:absolute;
  z-index:100;
  left:50%;
  bottom:calc(100% + 8px);
  width:max-content;
  max-width:300px;
  transform:translateX(-50%);
  border:1px solid #334554;
  border-radius:8px;
  background:#0b1218;
  color:#dce5ec;
  padding:8px 10px;
  font-size:11px;
  font-weight:500;
  line-height:1.4;
  letter-spacing:0;
  text-transform:none;
  box-shadow:0 10px 28px rgba(0,0,0,.35);
  opacity:0;
  pointer-events:none;
  transition:opacity .12s ease;
}
.help-tip:hover::after,.help-tip:focus::after{opacity:1}
.help-tip:focus{outline:1px solid #6992ad;outline-offset:2px}
[data-help]:not(.help-tip){position:relative}
.operator-command{
  display:grid;
  gap:var(--veridra-gap);
}
.operator-hero{
  display:grid;
  grid-template-columns:minmax(0,1.7fr) minmax(290px,.8fr);
  gap:var(--veridra-gap);
}
.operator-primary,.operator-guide,.operator-module{
  padding:16px 18px;
  background:linear-gradient(180deg,rgba(12,29,42,.92),rgba(8,21,31,.94));
  border:1px solid var(--veridra-border);
  border-radius:var(--veridra-radius);
}
.operator-primary h1{margin:4px 0 7px}
.operator-primary p{max-width:820px;margin:0 0 14px;color:var(--veridra-text-secondary)}
.operator-guide h2{margin:3px 0 8px}
.operator-guide p{margin:0;color:var(--veridra-text-secondary)}
.operator-guide .guardrail{margin-top:12px;padding-top:10px;border-top:1px solid #1b2832}
.operator-flow{
  display:grid;
  grid-template-columns:repeat(5,minmax(0,1fr));
  gap:8px;
}
.operator-flow .step{
  min-height:72px;
  padding:10px 11px!important;
}
.operator-flow .step strong{
  display:flex;
  align-items:center;
  gap:6px;
  margin:0 0 4px;
  font-size:11px;
}
.operator-flow .step span{font-size:10px;line-height:1.35}
.flow-number{
  display:inline-grid;
  place-items:center;
  width:19px;
  height:19px;
  border:1px solid #355069;
  border-radius:999px;
  color:#9bc7e7;
  font-size:9px;
}
.operator-modules{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:var(--veridra-gap);
}
.operator-module{min-height:150px;display:flex;flex-direction:column}
.operator-module h2{margin:4px 0 7px}
.operator-module p{margin:0 0 12px;color:var(--veridra-text-secondary);font-size:11px}
.operator-module .actions{margin-top:auto}
.operator-module .module-state{
  margin-top:auto;
  padding-top:10px;
  border-top:1px solid #1b2832;
  color:#718493;
  font-size:9px;
  text-transform:uppercase;
  letter-spacing:.07em;
}
@media(min-width:1200px) and (min-height:800px){
  body:has(.agency-workbench){overflow:hidden}
  body>main:has(.agency-workbench){height:100vh;overflow:hidden;padding-bottom:16px!important}
  .agency-workbench{height:100%;min-height:0}
  .agency-workbench:not(:has(.operator-command)){display:flex;flex-direction:column;gap:10px}
  .agency-workbench:not(:has(.operator-command)) .workbench-body{
    flex:1 1 auto;min-height:0;overflow:hidden
  }
  .agency-workbench:not(:has(.operator-command)) .workbench-scroll,
  .agency-workbench:not(:has(.operator-command)) .workbench-cards{height:100%;overflow:auto}
  .workbench-split{
    display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);
    gap:10px;height:100%;min-height:0
  }
  .workbench-split>*{min-width:0}
  .workbench-split>*{min-height:0;overflow:auto}
}
@media(max-width:1100px){
  .agency-nav{grid-template-columns:auto minmax(0,1fr)}
  .nav-context{display:none}
  .operator-modules{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:800px){
  body>main{padding:112px 14px 18px!important}
  .agency-nav{grid-template-columns:1fr;padding:8px 12px!important}
  .agency-nav .nav-brand{justify-content:space-between}
  .agency-nav .nav-links{width:100%}
  .operator-hero{grid-template-columns:1fr}
  .operator-flow{grid-template-columns:repeat(2,minmax(0,1fr))}
  .operator-modules{grid-template-columns:1fr}
}
</style>
"""


def agency_design_system() -> str:
    return AGENCY_DESIGN_SYSTEM


def help_tip(text: str, *, label: str = "Help") -> str:
    safe = html.escape(text, quote=True)
    safe_label = html.escape(label, quote=True)
    return (
        f"<span class='help-tip' tabindex='0' role='note' "
        f"aria-label='{safe_label}: {safe}' data-help='{safe}'>?</span>"
    )
