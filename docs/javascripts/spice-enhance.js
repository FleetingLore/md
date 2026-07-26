/**
 * SPICE block toolbar: edit / copy / data / chart
 * All simulation runs server-side via /raw and /render endpoints.
 */
document$.subscribe(() => {
  document.querySelectorAll("code.language-spice").forEach(enhanceBlock);
  document.querySelectorAll('.spice-block').forEach(function(block) {
    var pre = block.querySelector('.spice-code-area pre code') || block.querySelector('.spice-code-area pre');
    if (!pre || block.dataset.wasmHooked) return;
    block.dataset.wasmHooked = '1';
    block.dataset.original = pre.textContent || '';
    updateSimButtons(block, block.dataset.original);
    // buttons always enabled (server-side)
    block.querySelectorAll('.spice-data-btn,.spice-chart-btn').forEach(function(b) {
      b.style.pointerEvents = ''; b.style.opacity = '';
    });
  });
});

var API = (document.querySelector('meta[name="spice-api"]')||{}).content||'';

/* ================================================================ */
const CHECK_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';

/* helpers */
const $ = (el, sel) => el.closest('.spice-block').querySelector(sel);
const getPre  = el => $(el, '.spice-code-area pre code') || $(el, '.spice-code-area pre');
const getTa   = el => $(el, '.spice-code-area textarea');
const textOf  = el => { const ta = getTa(el); return ta ? ta.value : (getPre(el)||{}).textContent||''; };
const titleEl = el => $(el, '.spice-toolbar-title');
const editBtn = el => $(el, '.spice-edit-btn');
const copyBtn = el => $(el, '.spice-copy-btn');

/* ================================================================ */
/* copy                                                        */
/* ================================================================ */
function copySpiceNetlist(btn) {
  const text = textOf(btn);
  const done = () => {
    btn.style.background = 'rgba(255,255,255,0.12)';
    setTimeout(() => { btn.style.background = ''; }, 600);
  };
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    navigator.clipboard.writeText(text).then(done).catch(() => { /* silent */ });
  } else {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch(e) { /* silent */ }
    document.body.removeChild(ta);
    done();
  }
}

/* ================================================================ */
/* edit toggle                                                  */
/* ================================================================ */
function toggleEdit(eb) {
  const block = eb.closest('.spice-block');
  const area  = block.querySelector('.spice-code-area');
  const pre   = area.querySelector('pre');
  const cb    = copyBtn(eb);

  if (pre) {
    /* enter edit */
    const ta = document.createElement('textarea');
    ta.className = 'spice-netlist'; ta.spellcheck = false;
    ta.value = (pre.querySelector('code')||pre).textContent;
    ta.addEventListener('input', () => updateModified(block));
    area.replaceChild(ta, pre);
    eb.innerHTML = CHECK_ICON;
    if (cb.dataset.restore) {
      cb.innerHTML = cb.dataset.restore; cb.title = 'Restore';
      cb.onclick = null;
      cb.addEventListener('click', function r(){restoreNetlist(eb);cb.removeEventListener('click',r);}, {once:true});
    } else {
      console.warn('data-restore not found on copy button');
    }
    ta.focus();
    setActionButtons(block, false);
  } else {
    /* confirm (exit edit) */
    const textarea = area.querySelector('textarea');
    const newNetlist = textarea.value;
    const newPre = document.createElement('pre'); newPre.className = 'spice-netlist';
    const code = document.createElement('code'); code.className = 'language-spice';
    code.textContent = newNetlist; newPre.appendChild(code);
    area.replaceChild(newPre, textarea);
    eb.innerHTML = eb.dataset.edit;
    resetCopy(cb);
    updateModified(block);
      block.querySelectorAll('.spice-data-btn,.spice-chart-btn').forEach(function(b){
        b.style.pointerEvents='';b.style.opacity='';
      });
    if (newNetlist.trim() !== (block.dataset.original || '').trim()) {
      updateSimButtons(block, newNetlist);
    }
  }
}

function restoreNetlist(eb) {
  var block = eb.closest('.spice-block');
  var ta = getTa(eb);
  if (ta) { ta.value = block.dataset.original || ''; }
  updateModified(block);
}

function updateModified(block) {
  const orig = (block.dataset.original||'').trim();
  const curr = textOf(block).trim();
  titleEl(block).classList.toggle('modified', curr !== orig);
}

function resetCopy(cb) {
  cb.innerHTML = cb.dataset.icon; cb.title = 'Copy';
  cb.onclick = null;
  cb.addEventListener('click', function c(){copySpiceNetlist(cb);cb.removeEventListener('click',c);}, {once:true});
}

/* disable chart / data buttons while editing */
function setActionButtons(block, enabled, dataOnly) {
  var sel = dataOnly ? '.spice-data-btn' : '.spice-chart-btn,.spice-data-btn';
  block.querySelectorAll(sel).forEach(function(b) {
    b.style.pointerEvents = enabled ? '' : 'none';
    b.style.opacity = enabled ? '' : '0.35';
  });
}

/* ================================================================ */
/* update chart/data buttons after edit                            */
/* ================================================================ */
function updateSimButtons(block, netlist) {
  const chartBtns = block.querySelectorAll('.spice-chart-btn');
  const dataBtns  = block.querySelectorAll('.spice-data-btn');

  /* data button → POST to server */
  dataBtns.forEach(btn => {
    btn.onclick = async () => {
      showConnBar(); updateConnBar('发送请求...');
      try {
        var resp = await fetch(API+'/raw', { method: 'POST', body: netlist });
        updateConnBar('接收中...');
        if (!resp.ok) { updateConnBar('HTTP '+resp.status+' 错误'); setTimeout(removeConnBar,3000); return; }
        var txt = await resp.text();
        updateConnBar('HTTP '+resp.status+'  '+txt.split('\n').length+' 行  完成');
        setTimeout(removeConnBar,2500);
        openSpiceData(btoa(String.fromCharCode(...new TextEncoder().encode(txt))));
      } catch(e) {
        updateConnBar('连接失败: '+e.message); setTimeout(removeConnBar,3000);
      }
    };
  });

  /* chart buttons → POST to server */
  chartBtns.forEach(btn => {
    btn.onclick = async () => {
      showConnBar(); updateConnBar('发送请求...');
      try {
        var resp = await fetch(API+'/render', { method: 'POST', body: netlist });
        updateConnBar('接收中...');
        if (!resp.ok) { updateConnBar('HTTP '+resp.status+' 错误'); setTimeout(removeConnBar,3000); return; }
        var svg = await resp.text();
        updateConnBar('HTTP '+resp.status+'  '+(svg.length/1000).toFixed(1)+'KB  完成');
        setTimeout(removeConnBar,2500);
        openChartSVG(svg);
      } catch(e) {
        updateConnBar('连接失败: '+e.message); setTimeout(removeConnBar,3000);
      }
    };
  });
}

/* ================================================================ */
/* connection status bar                                           */
/* ================================================================ */
function showConnBar() {
  if (document.getElementById('__conn_bar')) return;
  var bar = document.createElement('div'); bar.id = '__conn_bar';
  bar.innerHTML = '<div style="position:fixed;bottom:1rem;left:10%;width:80%;padding:0.5rem 0.8rem;background:rgba(0,0,0,0.4);color:#6cffca;font-size:0.78rem;font-family:sans-serif;border-radius:6px;z-index:9999;box-shadow:0 2px 12px rgba(0,0,0,0.5);display:flex;justify-content:space-between;align-items:center">'+
    '<span style="display:flex;align-items:center;gap:0.4rem"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6cffca" stroke-width="2" style="animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"/><path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"/></svg>连接服务器</span>'+
    '<span id="__conn_msg"></span>'+
    '</div><style>@keyframes spin{to{transform:rotate(360deg)}}</style>';
  document.body.appendChild(bar);
}
function updateConnBar(m) {
  var b = document.getElementById('__conn_msg');
  if (b) b.textContent = m;
}
function removeConnBar() {
  var b = document.getElementById('__conn_bar');
  if (b) b.remove();
}

/* ================================================================ */
/* chart / data popups                                             */
/* ================================================================ */
function openChartSVG(svg) {
  const h = '<!DOCTYPE html><html style="background:#737373"><head><meta charset="utf-8"><style>'
    + 'html,body{margin:0;background:#737373;display:flex;align-items:center;justify-content:center;min-height:100vh}'
    + 'svg{max-width:100vw;max-height:100vh}</style></head><body>' + svg + '</body></html>';
  window.open(URL.createObjectURL(new Blob([h],{type:'text/html'})), '_blank', 'noopener');
}

function openSpiceData(b64) {
  const bin = atob(b64); const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
  const txt = new TextDecoder().decode(bytes).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const h = '<!DOCTYPE html><html style="background:#737373"><head><meta charset="utf-8"><style>'
    + 'html,body{margin:0;background:#737373;color:#fff;font:14px/1.6 monospace;padding:2rem}'
    + 'pre{white-space:pre-wrap;word-break:break-all}</style></head><body><pre>' + txt + '</pre></body></html>';
  window.open(URL.createObjectURL(new Blob([h],{type:'text/html'})), '_blank', 'noopener');
}

/* ================================================================ */
/* plain ```spice blocks (outside .spice-block)                   */
/* ================================================================ */
function enhanceBlock(code) {
  const pre = code.closest("pre");
  if (!pre || pre.dataset.spiceEnhanced) return;
  if (pre.closest(".spice-block")) return;
  pre.dataset.spiceEnhanced = "1";
  const tb = document.createElement("div"); tb.className = "spice-toolbar";
  const b1 = document.createElement("button"); b1.textContent = "Copy";
  b1.onclick = () => {
    const text = code.textContent || "";
    const done = () => { b1.textContent='✓ Copied'; setTimeout(()=>b1.textContent='Copy',1500); };
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      navigator.clipboard.writeText(text).then(done).catch(() => {});
    } else {
      const ta=document.createElement('textarea'); ta.value=text; ta.style.position='fixed';
      ta.style.left='-9999px'; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch(e) {}
      document.body.removeChild(ta); done();
    }
  };
  tb.appendChild(b1);
  pre.parentNode.insertBefore(tb, pre);
}
