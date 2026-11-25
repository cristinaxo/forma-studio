'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const paths = {
 sliders:'<path d="M4 7h6m4 0h6M4 17h10m4 0h2"/><circle cx="12" cy="7" r="2"/><circle cx="16" cy="17" r="2"/>',
 folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10H3Z"/>',
 mic:'<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 10v2a6 6 0 0 0 12 0v-2M12 18v3m-3 0h6"/>',
 layers:'<path d="m12 3 10 5-10 5L2 8Zm-9 10 9 5 9-5M3 18l9 4 9-4"/>',
 spark:'<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7ZM19 2v4m-2-2h4"/>',
 map:'<path d="m3 5 6-2 6 3 6-2v15l-6 2-6-3-6 2ZM9 3v15m6-12v15"/>',
 help:'<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 4 3v2m-1 3h.01"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 wave:'<path d="M3 10v4m4-7v10m5-14v18m5-14v10m4-7v4"/>',
 upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/>',
 music:'<path d="M9 18V5l11-2v13M9 9l11-2"/><ellipse cx="6" cy="18" rx="3" ry="2"/><ellipse cx="17" cy="16" rx="3" ry="2"/>',
 close:'<path d="m6 6 12 12M6 18 18 6"/>',
 shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Zm-4 9 3 3 5-6"/>',
 balance:'<path d="M12 3v17m-5 1h10M4 7h16M6 7l-4 8h8Zm12 0-4 8h8Z"/>',
 sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
 bolt:'<path d="m14 2-9 12h7l-2 8 9-12h-7Z"/>',
 file:'<path d="M5 3h9l5 5v13H5ZM14 3v6h5M8 13h8m-8 4h6"/>',
 circle:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
 search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
 download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
 trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
 check:'<path d="m5 12 4 4L19 6"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.wave}</svg>`;
function icons(root=document) { root.querySelectorAll('[data-icon]').forEach(el => el.innerHTML = icon(el.dataset.icon)); }
icons();
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time = s => `${Math.floor(s/60).toString().padStart(2,'0')}:${Math.floor(s%60).toString().padStart(2,'0')}`;
const toolNames = {master:'Mastering',voice:'Voice conversion',stems:'Stem splitter'};
const toolIcons = {master:'spark',voice:'mic',stems:'layers'};
const state = {tool:'master',preset:'balanced',file:null,reference:null,projects:[],active:null,submitting:false,recording:false,engine:null,objectURL:null,referenceURL:null,buffer:null,recorder:null,stream:null,recordTimer:null,recordStart:0,view:'studio'};
let toastTimer, pollTimer;
function toast(message) { $('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,6500); }
async function api(path,options={}) { const res=await fetch(path,options);const data=await res.json();if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:'Unable to complete that request. Check the settings and try again.');return data; }
function showView(view) {state.view=view;$('#studio-view').hidden=view!=='studio';$('#projects-view').hidden=view!=='projects';$('#nav-studio').classList.toggle('active',view==='studio');$('#nav-projects').classList.toggle('active',view==='projects');$('#breadcrumb').textContent=view==='studio'?'Studio':'My projects';if(view==='projects')renderProjects();window.scrollTo({top:0,behavior:'smooth'});}
function selectTool(tool) {
 if(state.recording || state.submitting)return;
 state.tool=tool;showView('studio');$$('.tool-card').forEach(x=>x.classList.toggle('selected',x.dataset.tool===tool));
 ['master','voice','stems'].forEach(t=>$(`#${t}-settings`).hidden=t!==tool);
 $('#reference-section').hidden=tool!=='voice';
 $('#settings-title').textContent={master:'Make it shine',voice:'Find a new voice',stems:'Take it apart'}[tool];
 $('#process-label').textContent={master:'Master this track',voice:'Convert this voice',stems:'Separate this track'}[tool];
 $('#process-button [data-icon]').innerHTML=icon(toolIcons[tool]);
 $('#file-limit').textContent=tool==='voice'?'UP TO 30 SECONDS':'UP TO 3 MINUTES';
 $('#output-detail').textContent=tool==='voice'?'Local voice model':tool==='stems'?'4 individual stems':'24-bit output';
 updateButton();
}
const DEFAULT_STEPS={speech:'10',singing:'30'};
function applyModeDefaults(){const mode=$('#voice-mode').value;$('#voice-steps').value=DEFAULT_STEPS[mode]||'10';}
function newSeed(){$('#seed').value=String(Math.floor(Math.random()*2147483647));}
function updateButton(){ $('#process-button').disabled=!state.file || state.submitting || state.recording || (state.tool==='voice'&&!state.reference) || !state.engine; }
function clearFile(){state.file=null;state.buffer=null;$('#audio-file').value='';$('#loaded-audio').hidden=true;$('#drop-area').hidden=false;$('#input-player').pause();$('#input-player').removeAttribute('src');if(state.objectURL)URL.revokeObjectURL(state.objectURL);state.objectURL=null;updateButton();}
async function loadFile(file) {
 if(!file)return;
 if(file.size>50*1024*1024)return toast('Choose a file under 50 MB.');
 if(!file.size)return toast('This file is empty. Choose another recording.');
 clearFile();state.file=file;state.objectURL=URL.createObjectURL(file);$('#input-player').src=state.objectURL;$('#file-name').textContent=file.name;$('#file-info').textContent=`${(file.size/1024/1024).toFixed(1)} MB · Original audio`;
 $('#drop-area').hidden=true;$('#loaded-audio').hidden=false;
 if(!$('#project-name').value)$('#project-name').value=file.name.replace(/\.[^.]+$/,'');
 updateButton();
 let context;
 try{context=new AudioContext();const buffer=await context.decodeAudioData(await file.arrayBuffer());if(state.file!==file)return;state.buffer=buffer;$('#duration-label').textContent=time(buffer.duration);$('#file-info').textContent=`${time(buffer.duration)} · ${(buffer.sampleRate/1000).toFixed(1)} kHz · ${buffer.numberOfChannels===1?'Mono':'Stereo'}`;drawWaveform();}catch{toast('Waveform preview is unavailable for this format. The local engine will try to decode it.');}finally{if(context)await context.close();}
}
function drawWaveform(){const canvas=$('#waveform');if(!state.buffer)return;const rect=canvas.getBoundingClientRect(),ratio=window.devicePixelRatio||1;canvas.width=rect.width*ratio;canvas.height=rect.height*ratio;const c=canvas.getContext('2d');c.scale(ratio,ratio);const w=rect.width,h=rect.height,data=state.buffer.getChannelData(0),bars=Math.floor(w/4),step=Math.max(1,Math.floor(data.length/bars));c.strokeStyle='#dce4d0';c.beginPath();c.moveTo(0,h/2);c.lineTo(w,h/2);c.stroke();for(let i=0;i<bars;i++){let peak=0;for(let j=i*step;j<Math.min((i+1)*step,data.length);j+=Math.max(1,Math.floor(step/70)))peak=Math.max(peak,Math.abs(data[j]));const height=Math.max(2,peak*(h-42));c.fillStyle=i/bars<($('#input-player').currentTime/(state.buffer.duration||1))?'#6f8b48':'#a9bb8c';c.fillRect(i*4,(h-height)/2,2,height);}}
async function record(){
 if(state.recording){state.recorder.stop();return;}
 if(!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)return toast('Recording is unavailable in this browser. Upload an audio file instead.');
 try{
  state.stream=await navigator.mediaDevices.getUserMedia({audio:true});
  const mime=['audio/webm;codecs=opus','audio/mp4','audio/webm'].find(x=>MediaRecorder.isTypeSupported(x));
  state.recorder=new MediaRecorder(state.stream,mime?{mimeType:mime}:{});const chunks=[];
  state.recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
  state.recorder.onstop=()=>{clearInterval(state.recordTimer);state.stream.getTracks().forEach(t=>t.stop());state.recording=false;$('#record-button').classList.remove('recording');$('#record-label').textContent='Record audio';$('#record-copy').textContent='Or catch an idea while it’s fresh.';const type=state.recorder.mimeType,ext=type.includes('mp4')?'m4a':'webm';loadFile(new File(chunks,`Recording ${new Date().toLocaleTimeString().replaceAll(':','-')}.${ext}`,{type}));};
  state.recorder.start(1000);state.recording=true;state.recordStart=Date.now();$('#record-button').classList.add('recording');$('#record-label').textContent='Stop recording';$('#record-copy').textContent='Recording 00:00';updateButton();
  state.recordTimer=setInterval(()=>{const seconds=(Date.now()-state.recordStart)/1000;$('#record-copy').textContent=`Recording ${time(seconds)}`;if(seconds>=(state.tool==='voice'?30:180))state.recorder.stop();},500);
 }catch(e){state.stream?.getTracks().forEach(t=>t.stop());toast('Microphone access was not available. Allow access in your browser or upload a file.');}
}
async function processAudio(){
 if(!state.file || state.submitting)return;
 const limit=state.tool==='voice'?30:180;
 if(state.buffer?.duration>limit)return toast(`This tool accepts clips up to ${limit} seconds. Choose a shorter file.`);
 state.submitting=true;updateButton();$('#process-label').textContent='Preparing your audio…';
 const data=new FormData();data.append('source',state.file);data.append('tool',state.tool);data.append('title',$('#project-name').value);data.append('preset',state.preset);data.append('target',$('#loudness').value);data.append('steps',$('#voice-steps').value);data.append('pitch',$('#pitch').value);data.append('mode',$('#voice-mode').value);data.append('seed',$('#seed').value);if(state.tool==='voice'&&state.reference)data.append('reference',state.reference);
 try{const item=await api('/api/projects',{method:'POST',body:data});state.active=item;renderResult(item);await refresh();$('#active-result').scrollIntoView({behavior:'smooth',block:'nearest'});}catch(e){toast(e.message);}finally{state.submitting=false;selectTool(state.tool);}
}
function renderResult(item){
 const el=$('#active-result');el.hidden=false;
 const working=['running','queued'].includes(item.status);
 const elapsed=item.started?Math.max(0,Math.floor((Date.now()/1000)-item.started)):0;
 const stats=item.analysis;
 el.innerHTML=`<div class="result-heading"><div class="result-indicator">${working?'<span class="spinner"></span>':`<span style="color:#8fa861">${icon(item.status==='success'?'check':'wave')}</span>`}<div><h2>${escapeHTML(item.title)}</h2><p>${toolNames[item.tool]} · ${working?(item.status==='queued'?'In the local queue':`Processing · ${time(elapsed)} elapsed`):escapeHTML(item.status==='success'?'Your audio is ready':item.status)}</p></div></div>${working?'<button class="secondary" id="cancel-job">Stop job</button>':'<button class="icon-button" id="close-result" aria-label="Close result">'+icon('close')+'</button>'}</div>
 ${item.status!=='success'?`<p class="result-message ${item.status==='error'?'error':''}">${escapeHTML(item.message)}</p>${working?'<p class="result-note">You can keep working while this runs. The first use of a model may download its weights. Your audio stays local.</p>':''}`:''}
 ${stats&&stats.seed!=null?`<div class="stats-row"><div>Take seed<b>${stats.seed}</b></div><div>Detail<b>${stats.steps} <small>STEPS</small></b></div><div>Pitch<b>${stats.pitch>0?'+':''}${String(stats.pitch).replace('-','−')} <small>ST</small></b></div><div>Device<b>${escapeHTML(String(stats.device).toUpperCase())}</b></div></div><p class="result-note">Reproduce this take with the same seed, detail, mode, pitch and device. Checkpoint: ${escapeHTML(stats.checkpoint||'—')}.</p>`:''}
 ${stats&&stats.input_lufs!=null?`<div class="stats-row"><div>Original loudness<b>${stats.input_lufs} <small>LUFS</small></b></div><div>Mastered loudness<b>${stats.output_lufs} <small>LUFS</small></b></div><div>True peak estimate<b>${stats.true_peak_dbtp} <small>dBTP</small></b></div>${stats.max_gain_reduction_db==null?'':`<div>Max gain reduction<b>${stats.max_gain_reduction_db} <small>dB</small></b></div>`}</div>${stats.target_reached===false?`<p class="result-note">The ${stats.target_lufs} LUFS target was not reachable without over-limiting, so this master stops at ${stats.output_lufs} LUFS and keeps its transients.</p>`:''}`:''}
 ${(item.outputs||[]).length?`<div class="output-track"><div>Original<small>Compare your source</small></div><audio controls preload="metadata" src="${escapeHTML(item.source_url)}"></audio><a href="${escapeHTML(item.source_url)}" download="original.wav" aria-label="Download original">${icon('download')}</a></div>`:''}
 ${(item.outputs||[]).map(o=>`<div class="output-track"><div>${escapeHTML(o.name)}<small>${time(o.duration)} · WAV · ${(o.bytes/1024/1024).toFixed(1)} MB</small></div><audio controls preload="metadata" src="${escapeHTML(o.url)}"></audio><a href="${escapeHTML(o.url)}" download="${escapeHTML(o.file)}" aria-label="Download ${escapeHTML(o.name)}">${icon('download')}</a></div>`).join('')}`;
 $('#cancel-job')?.addEventListener('click',async()=>{try{await api(`/api/projects/${item.id}/cancel`,{method:'POST'});await refresh();}catch(e){toast(e.message);}});
 $('#close-result')?.addEventListener('click',()=>{state.active=null;el.hidden=true;});
 el.querySelectorAll('audio').forEach(player=>player.addEventListener('play',()=>$$('audio').forEach(other=>{if(other!==player)other.pause();})));
}
function row(item){return `<div class="project-row"><span class="tool-icon ${item.tool==='voice'?'voice-icon':item.tool==='stems'?'stem-icon':'master-icon'}">${icon(toolIcons[item.tool])}</span><button class="project-info" data-open="${item.id}"><strong>${escapeHTML(item.title)}</strong><small>${toolNames[item.tool]} · ${time(item.duration)} · ${new Date(item.created*1000).toLocaleDateString(undefined,{month:'short',day:'numeric'})}</small></button><span class="project-state ${item.status}">${item.status==='success'?'Ready':escapeHTML(item.status)}</span>${!['running','queued'].includes(item.status)?`<button class="icon-button" data-delete="${item.id}" aria-label="Delete ${escapeHTML(item.title)}">${icon('trash')}</button>`:''}</div>`;}
function empty(){return `<div class="empty-projects"><span>${icon('folder')}</span><div><strong>A clean slate. A new possibility.</strong><p>Your processed tracks will appear here, ready whenever you are.</p></div><span class="empty-end">Make your first track ↑</span></div>`;}
function wireRows(root){root.querySelectorAll('[data-open]').forEach(b=>b.addEventListener('click',()=>{state.active=state.projects.find(p=>p.id===b.dataset.open);showView('studio');renderResult(state.active);$('#active-result').scrollIntoView({behavior:'smooth',block:'center'});}));root.querySelectorAll('[data-delete]').forEach(b=>b.addEventListener('click',()=>confirmDelete(b.dataset.delete)));}
function renderProjects(){
 $('#project-count').textContent=state.projects.length;
 $('#recent-list').innerHTML=state.projects.length?state.projects.slice(0,3).map(row).join(''):empty();wireRows($('#recent-list'));
 const query=$('#project-search').value.toLowerCase(),found=state.projects.filter(p=>p.title.toLowerCase().includes(query));
 $('#projects-list').innerHTML=found.length?found.map(row).join(''):(query?'<div class="empty-projects">No projects match your search.</div>':empty());wireRows($('#projects-list'));
}
async function refresh(){
 try{
  state.projects=await api('/api/projects');renderProjects();
  if(state.active){const updated=state.projects.find(p=>p.id===state.active.id);if(updated){const previous=state.active;state.active=updated;if(['queued','running'].includes(previous.status)||previous.status!==updated.status)renderResult(updated);}}
 }catch(e){/* The connection state is surfaced by the engine heartbeat. */}
}
function dialog(html){$('#dialog-content').innerHTML=html;$('#info-dialog').showModal();}
function confirmDelete(id){const item=state.projects.find(p=>p.id===id);dialog(`<div class="eyebrow">REMOVE A SESSION</div><h2>Delete this project?</h2><p>“${escapeHTML(item.title)}” and its saved audio files will be removed from this computer.</p><button class="dark-button" id="confirm-delete">Delete project</button>`);$('#confirm-delete').onclick=async()=>{try{await api(`/api/projects/${id}`,{method:'DELETE'});$('#info-dialog').close();if(state.active?.id===id){state.active=null;$('#active-result').hidden=true;}await refresh();toast('Project deleted.');}catch(e){toast(e.message);}};}
function engineDialog(){const e=state.engine;dialog(`<div class="eyebrow">INDEPENDENT BY DESIGN</div><h2>Your local audio engine.</h2><p>Audio is processed on your own computer. No paid API or cloud processing service is connected.</p><div class="detail-row"><span>Mastering · EQ, compression, limiter</span><span>${e?'Installed':'Offline'}</span></div><div class="detail-row"><span>Stem separation · Demucs</span><span>${e?.stems?'Installed':'Not available'}</span></div><div class="detail-row"><span>Voice conversion · Seed-VC</span><span>${e?.voice?'Installed':'Not available'}</span></div><div class="detail-row"><span>Processing device</span><span>${e?.device||'—'}</span></div><p>Models download on first use. Longer clips and higher detail take more time. The model code and weights are cached locally.</p><div class="phase-label">YOUR AUDIO IS SAVED HERE</div><p class="path">${escapeHTML(e?.data_directory||'Connect to the local engine first.')}</p>`);}
async function heartbeat(){try{state.engine=await api('/api/status');$('#engine-status').innerHTML='<i></i> Local engine online';$('#engine-status').classList.remove('offline');}catch{state.engine=null;$('#engine-status').innerHTML='<i></i> Engine offline';$('#engine-status').classList.add('offline');}updateButton();}
$$('[data-tool]').forEach(b=>b.addEventListener('click',()=>selectTool(b.dataset.tool)));
$$('[data-preset]').forEach(b=>b.addEventListener('click',()=>{state.preset=b.dataset.preset;$$('[data-preset]').forEach(x=>x.classList.toggle('selected',x===b));}));
$('#loudness').addEventListener('input',e=>$('#loudness-value').textContent=e.target.value.replace('-','−'));
$('#pitch').addEventListener('input',e=>$('#pitch-value').textContent=(e.target.value>0?'+':'')+e.target.value.replace('-','−'));
$('#voice-mode').addEventListener('change',applyModeDefaults);
$('#new-take').addEventListener('click',newSeed);
$('#upload-button').onclick=e=>{e.stopPropagation();$('#audio-file').click();};
$('#drop-area').onclick=()=>$('#audio-file').click();$('#drop-area').onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();$('#audio-file').click();}};
$('#audio-file').onchange=e=>loadFile(e.target.files[0]);
$('#drop-area').ondragover=e=>{e.preventDefault();$('#drop-area').classList.add('drag-over');};
$('#drop-area').ondragleave=()=>$('#drop-area').classList.remove('drag-over');
$('#drop-area').ondrop=e=>{e.preventDefault();$('#drop-area').classList.remove('drag-over');loadFile(e.dataTransfer.files[0]);};
$('#remove-file').onclick=clearFile;
$('#reference-file').onchange=e=>{const file=e.target.files[0];if(!file)return;if(file.size>50*1024*1024){e.target.value='';return toast('Reference audio must be under 50 MB.');}state.reference=file;if(state.referenceURL)URL.revokeObjectURL(state.referenceURL);state.referenceURL=URL.createObjectURL(file);$('#reference-label').textContent=file.name;$('#reference-player').src=state.referenceURL;$('#reference-player').hidden=false;updateButton();};
$('#record-button').onclick=record;$('#process-button').onclick=processAudio;
function newSession(){if(state.recording||state.submitting)return;clearFile();state.reference=null;$('#reference-file').value='';$('#reference-label').textContent='Choose reference audio';$('#reference-player').pause();$('#reference-player').hidden=true;if(state.referenceURL)URL.revokeObjectURL(state.referenceURL);state.referenceURL=null;$('#project-name').value='';$('#pitch').value='0';$('#pitch-value').textContent='0';applyModeDefaults();state.active=null;$('#active-result').hidden=true;showView('studio');}
$('#new-session').onclick=newSession;$('#back-studio').onclick=newSession;$('#nav-studio').onclick=()=>showView('studio');$('#nav-projects').onclick=()=>showView('projects');$('#view-all').onclick=()=>showView('projects');$('#project-search').oninput=renderProjects;
$('#engine-button').onclick=engineDialog;
$('#help-button').onclick=()=>dialog('<div class="eyebrow">FIND YOUR FLOW</div><h2>From an idea to a track.</h2><p>1. Choose a tool, then upload or record audio.<br>2. Set the character, stems, or reference voice.<br>3. Start processing. Listen and download the results.</p><p>Mastering and stem splitting accept up to 3 minutes. Voice conversion accepts up to 30 seconds, with a clean 3–30 second reference recording.</p><p>Every completed session is saved in My projects. Keep this local server running while processing. You can close the browser and return later.</p>');
$('#roadmap-button').onclick=()=>dialog('<div class="eyebrow">ONE GOOD STEP AT A TIME</div><h2>The studio is growing.</h2><div class="phase-label">01 · CORE STUDIO</div><p>Recording, voice conversion, four-stem separation, mastering, and saved sessions.</p><div class="phase-label">02 · CREATION TOOLS · PLANNED</div><p>Vocal generation, a voice designer, and harmony generation.</p><div class="phase-label">03 · FULL WORKSPACE · PLANNED</div><p>A larger voice library, advanced editing, batch workflows, and expanded audio tools.</p><p>Phase 2 and 3 features are planned, not available in this version.</p>');
$('.dialog-close').onclick=()=>$('#info-dialog').close();$('#info-dialog').addEventListener('click',e=>{if(e.target===$('#info-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
$('#input-player').addEventListener('timeupdate',drawWaveform);$('#input-player').addEventListener('play',()=>$$('audio').forEach(x=>{if(x!==$('#input-player'))x.pause();}));
window.addEventListener('resize',drawWaveform);
window.addEventListener('beforeunload',()=>state.stream?.getTracks().forEach(t=>t.stop()));
heartbeat();refresh();pollTimer=setInterval(refresh,3000);setInterval(heartbeat,15000);
